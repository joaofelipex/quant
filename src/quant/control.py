"""Painel de controle do runner ao vivo: estado em tempo real e kill-switch, atras do nginx (HTTPS + senha).

    QUANT_STATE=/var/lib/quant/live_state.json QUANT_KILL_FILE=/var/lib/quant/KILL python -m quant.control

Escuta so em 127.0.0.1 (o nginx faz proxy em /controle/). Biblioteca padrao apenas. O que ele PODE fazer: ler o estado
do runner e o journal, criar o arquivo KILL, ligar/parar/reiniciar o servico do runner (polkit restrito a essa unit) e
gravar parametros VALIDADOS num arquivo proprio (``runtime.env``, sem segredos). O que NAO faz, de proposito:
enviar ordem, aceitar modo ``live`` ou Polymarket (so por edicao na VM), apagar o KILL (retomar depois de kill e decisao
humana, ver deploy/README.md), ler ou gravar chaves.
"""
from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVICE = "quant-live"
ENV_WHITELIST = ("QUANT_MODE", "QUANT_VENUE", "QUANT_SYMBOL", "QUANT_TIMEFRAME", "QUANT_QTY", "QUANT_MAX_DAILY_LOSS",
                 "QUANT_STOP_ATR", "QUANT_TESTNET_KIND")
RUNTIME_ENV = Path("/var/lib/quant/runtime.env")
VERBS = ("start", "stop", "restart")


class SettingError(ValueError):
    pass


def _enum(*opts):
    def check(v: str) -> str:
        if v not in opts:
            raise SettingError(f"valor invalido {v!r}; use um de {', '.join(opts)}")
        return v
    return check


def _num(lo: float, hi: float):
    def check(v: str) -> str:
        try:
            x = float(v)
        except ValueError:
            raise SettingError(f"{v!r} nao e numero") from None
        if not (lo < x <= hi) or math.isnan(x):
            raise SettingError(f"{v} fora do intervalo ({lo}, {hi}]")
        return format(x, "g")
    return check


# so o que o navegador pode mudar; live e polymarket (sem testnet) ficam de fora de proposito
SETTINGS = {
    "QUANT_MODE": _enum("paper", "testnet"),
    "QUANT_VENUE": _enum("binance", "kalshi"),
    "QUANT_TIMEFRAME": _enum("1m", "5m", "15m", "1h"),
    "QUANT_QTY": _num(0, 1.0),
    "QUANT_MAX_DAILY_LOSS": _num(0, 1000),
    "QUANT_STOP_ATR": _num(0, 10),
}


def read_runtime(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def write_runtime(path: Path, updates: dict) -> dict[str, str]:
    """Valida (whitelist + tipos + faixas) e grava de forma atomica; levanta SettingError sem gravar nada."""
    unknown = set(updates) - set(SETTINGS)
    if unknown:
        raise SettingError(f"parametro nao permitido: {', '.join(sorted(unknown))}")
    clean = {k: SETTINGS[k](str(v).strip()) for k, v in updates.items()}
    merged = {**read_runtime(path), **clean}
    tmp = path.with_suffix(".tmp")
    body = "".join(f"{k}={v}" + chr(10) for k, v in sorted(merged.items()))
    tmp.write_text("# gerado por quant.control; sem segredos" + chr(10) + body)
    tmp.replace(path)
    return merged


def runner_action(verb: str, kill_file: Path, run=None) -> dict:
    """start/stop/restart do servico do runner. Com KILL presente nao liga: retomar e decisao humana."""
    if verb not in VERBS:
        raise SettingError(f"acao invalida {verb!r}")
    if verb in ("start", "restart") and kill_file.exists():
        return {"ok": False, "erro": "arquivo KILL presente: revise a posicao e remova-o na VM antes de ligar"}
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=30))
    r = run(["systemctl", verb, SERVICE])
    return {"ok": r.returncode == 0, "erro": (r.stderr or "").strip()[:300] if r.returncode else ""}
PAGE = Path(__file__).with_name("control.html")


def _run(cmd: list[str], timeout: float = 5) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def runner_config(pid: str | None = None) -> dict[str, str]:
    """Configuracao do runner (so chaves da whitelist) lida do ambiente do processo; nunca devolve chave de API."""
    pid = pid or _run(["systemctl", "show", SERVICE, "-p", "MainPID", "--value"])
    if not pid or pid == "0":
        return {}
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        return {}
    out = {}
    for item in raw:
        k, _, v = item.decode(errors="replace").partition("=")
        if k in ENV_WHITELIST:
            out[k] = v
    return out


def read_state(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


_BARS_CACHE: dict = {"t": 0.0, "key": None, "data": []}


def recent_closes(symbol: str, interval: str, n: int = 120, *, now: float | None = None) -> list[list[float]]:
    """[[ts_ms, close], ...] das ultimas barras fechadas do endpoint publico de spot (cache de 10 s); [] se falhar."""
    now = time.time() if now is None else now
    pair = symbol.split(":")[0].replace("/", "")
    key = (pair, interval, n)
    if _BARS_CACHE["key"] == key and now - _BARS_CACHE["t"] < 10:
        return _BARS_CACHE["data"]
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={pair}&interval={interval}&limit={n + 1}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            raw = json.load(r)[:-1]
        data = [[int(k[0]), float(k[4])] for k in raw]
    except (OSError, ValueError, KeyError, IndexError):
        data = []
    _BARS_CACHE.update({"t": now, "key": key, "data": data})
    return data


def service_health(unit: str = SERVICE, *, now: float | None = None) -> dict:
    """Saude do servico pelo systemd: ha quanto tempo esta ativo, reinicios e memoria."""
    out = _run(["systemctl", "show", unit, "-p", "ActiveEnterTimestamp", "-p", "NRestarts", "-p", "MemoryCurrent"])
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    uptime = None
    try:
        from datetime import datetime

        ts = datetime.strptime(kv["ActiveEnterTimestamp"].rsplit(" ", 1)[0], "%a %Y-%m-%d %H:%M:%S").timestamp()
        uptime = round((time.time() if now is None else now) - ts)  # o systemd mostra em UTC e a VM esta em UTC
    except (KeyError, ValueError):
        pass
    mem = kv.get("MemoryCurrent", "")
    return {"uptime_s": uptime, "restarts": int(kv["NRestarts"]) if kv.get("NRestarts", "").isdigit() else None,
            "memory_mb": round(int(mem) / 1e6, 1) if mem.isdigit() else None}


def portfolio_summary(log_path: Path, n: int = 60) -> dict | None:
    """Ultimos dias do paper da carteira (equity, pnl e pesos do ultimo dia) a partir do CSV do paper."""
    try:
        rows = list(csv.DictReader(log_path.read_text().splitlines()))
    except OSError:
        return None
    if not rows:
        return None

    def num(x):
        try:
            v = float(x)
            return None if math.isnan(v) else v
        except (TypeError, ValueError):
            return None

    last = rows[-1]
    return {"days": len(rows), "last_date": last["date"], "equity": num(last["equity"]), "pnl": num(last["pnl"]),
            "series": [[r["date"], num(r["equity"])] for r in rows[-n:]],
            "weights": {k[2:]: num(v) for k, v in last.items() if k.startswith("w_")}}


def build_status(state_path: Path, kill_file: Path, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    state = read_state(state_path)
    last_bar_age = None
    if state and state.get("last_bar"):
        try:
            import pandas as pd
            last_bar_age = round(now - pd.Timestamp(state["last_bar"], tz="UTC").timestamp())
        except (ValueError, TypeError):
            pass
    cfg = runner_config()
    return {
        "now": now,
        "bars": recent_closes(cfg.get("QUANT_SYMBOL", "ETH/USDT:USDT"), cfg.get("QUANT_TIMEFRAME", "1m")),
        "service": _run(["systemctl", "is-active", SERVICE]) or "desconhecido",
        "kill_file": kill_file.exists(),
        "config": cfg,
        "health": service_health(now=now),
        "portfolio": portfolio_summary(Path(os.environ.get("QUANT_PORT_LOG", "portfolio_log.csv"))),
        "state": state,
        "last_bar_age_s": last_bar_age,
        "log": _run(["journalctl", "-u", SERVICE, "-n", "40", "--no-pager", "-o", "short-iso"]).splitlines()[-40:],
    }


def trigger_kill(kill_file: Path) -> bool:
    kill_file.parent.mkdir(parents=True, exist_ok=True)
    kill_file.write_text(f"kill via painel em {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n")
    return kill_file.exists()


def make_handler(state_path: Path, kill_file: Path, runtime_path: Path = RUNTIME_ENV, run=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "quant-control"
        sys_version = ""

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj, default=str).encode(), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/status":
                self._json(200, build_status(state_path, kill_file))
            elif path == "/api/settings":
                self._json(200, {"saved": read_runtime(runtime_path), "effective": runner_config(),
                                 "options": {"QUANT_MODE": ["paper", "testnet"], "QUANT_VENUE": ["binance", "kalshi"],
                                             "QUANT_TIMEFRAME": ["1m", "5m", "15m", "1h"]}})
            else:
                self._json(404, {"erro": "nao encontrado"})

        def do_POST(self):  # noqa: N802
            # o navegador manda a senha do nginx sozinho: o cabecalho proprio barra CSRF (so JS da mesma origem)
            if self.headers.get("X-Quant-Control") != "1":
                return self._json(403, {"erro": "cabecalho X-Quant-Control ausente"})
            path = self.path.split("?")[0]
            if path == "/api/kill":
                ok = trigger_kill(kill_file)
                return self._json(200 if ok else 500, {"kill_file": ok})
            if path.startswith("/api/runner/"):
                try:
                    res = runner_action(path.rsplit("/", 1)[1], kill_file, run)
                except SettingError as e:
                    return self._json(404, {"ok": False, "erro": str(e)})
                return self._json(200 if res["ok"] else 409, res)
            if path == "/api/settings":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
                    if not isinstance(body, dict):
                        raise SettingError("corpo deve ser um objeto JSON")
                    return self._json(200, {"saved": write_runtime(runtime_path, body), "restart_needed": True})
                except (SettingError, ValueError) as e:
                    return self._json(400, {"erro": str(e)})
            self._json(404, {"erro": "nao encontrado"})

        def log_message(self, fmt, *args):  # noqa: A002
            print(f"{self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    state = Path(os.environ.get("QUANT_STATE", "live_state.json"))
    kill = Path(os.environ.get("QUANT_KILL_FILE", "KILL"))
    port = int(os.environ.get("QUANT_CONTROL_PORT", "8765"))
    runtime = Path(os.environ.get("QUANT_RUNTIME_ENV", str(RUNTIME_ENV)))
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, kill, runtime))
    print(f"quant.control em 127.0.0.1:{port} (estado={state}, kill={kill})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
