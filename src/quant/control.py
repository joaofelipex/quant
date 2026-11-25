"""Painel de controle do runner ao vivo: estado em tempo real e kill-switch, atras do nginx (HTTPS + senha).

    QUANT_STATE=/var/lib/quant/live_state.json QUANT_KILL_FILE=/var/lib/quant/KILL python -m quant.control

Escuta so em 127.0.0.1 (o nginx faz proxy em /controle/). Biblioteca padrao apenas. O que ele PODE fazer: ler o estado
do runner e o journal, criar o arquivo KILL, ligar/parar/reiniciar o servico do runner (polkit restrito a essa unit) e
gravar parametros VALIDADOS num arquivo proprio (``runtime.env``, sem segredos). O que NAO faz, de proposito:
enviar ordem por conta propria (a boleta manual so grava um pedido validado e dispara a unit ``quant-order``, que
e quem tem a chave, e so na demo), aceitar modo ``live`` ou Polymarket (so por edicao na VM), apagar o KILL
(retomar depois de kill e decisao humana, ver deploy/README.md), ler ou gravar chaves.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

SERVICE = "quant-live"
ENV_WHITELIST = ("QUANT_MODE", "QUANT_VENUE", "QUANT_SYMBOL", "QUANT_TIMEFRAME", "QUANT_QTY", "QUANT_MAX_DAILY_LOSS",
                 "QUANT_STOP_ATR", "QUANT_TESTNET_KIND", "QUANT_ASSETS", "QUANT_NOTIONAL", "QUANT_MAX_TOTAL_LOSS",
                 "QUANT_DONCHIAN", "QUANT_ER",
                 "QUANT_DIRECTION")
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


def _int(lo: int, hi: int):
    def check(v: str) -> str:
        try:
            x = int(float(v))
        except ValueError:
            raise SettingError(f"{v!r} nao e numero inteiro") from None
        if not (lo <= x <= hi):
            raise SettingError(f"{v} fora do intervalo [{lo}, {hi}]")
        return str(x)
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


def _assets(v: str) -> str:
    from .live import assets

    try:
        return ",".join(assets.parse(v))  # vazio = volta ao modo de um ativo so
    except ValueError as e:
        raise SettingError(str(e)) from None


# so o que o navegador pode mudar; live e polymarket (sem testnet) ficam de fora de proposito
SETTINGS = {
    "QUANT_MODE": _enum("paper", "testnet"),
    "QUANT_VENUE": _enum("binance", "kalshi"),
    "QUANT_TIMEFRAME": _enum("1m", "5m", "15m", "1h"),
    "QUANT_QTY": _num(0, 1.0),
    "QUANT_MAX_DAILY_LOSS": _num(0, 1000),
    "QUANT_STOP_ATR": _num(0, 10),
    "QUANT_DONCHIAN": _int(2, 500),
    "QUANT_ER": _num(0, 1),
    "QUANT_DIRECTION": _enum("both", "long"),
    "QUANT_ASSETS": _assets,
    "QUANT_NOTIONAL": _num(0, 1000),
    "QUANT_MAX_TOTAL_LOSS": _num(0, 100000),
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


def reset_risk(state_path: Path, kill_file: Path, run=None) -> dict:
    """Destrava a gestao de risco de todos os ativos: para o runner, zera ``halted`` e o PnL do dia nos estados e religa
    se ele estava ligado. NAO toca em posicoes, stops nem na entrada de cada estado: se sobrar posicao sem stop, o
    runner trava de novo sozinho ao subir. Recusa com o KILL presente (retomar apos kill e decisao humana, na VM)."""
    if kill_file.exists():
        return {"ok": False, "erro": "arquivo KILL presente: revise a posicao e remova-o na VM antes de destravar"}
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=30))
    was_active = run(["systemctl", "is-active", SERVICE]).stdout.strip() == "active"
    if was_active:
        r = run(["systemctl", "stop", SERVICE])  # o runner guarda o risco em memoria: so e seguro editar com ele parado
        if r.returncode:
            return {"ok": False, "erro": f"nao consegui parar o runner: {(r.stderr or '').strip()[:200]}"}
    changed = 0
    for f in sorted(state_path.parent.glob("live_state*.json")):
        if "paper" in f.name:
            continue
        st = read_state(f)
        if not st or not isinstance(st.get("risk"), dict):
            continue
        risk = st["risk"]
        if risk.get("halted") or risk.get("pnl") or risk.get("trades"):
            risk.update(halted=False, reason="", halt_daily=False, pnl=0.0, trades=0)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(st))
            tmp.replace(f)
            changed += 1
    started = ""
    if was_active:
        r = run(["systemctl", "start", SERVICE])
        started = "" if r.returncode == 0 else f"destravado, mas nao religou o runner: {(r.stderr or '').strip()[:200]}"
    return {"ok": not started, "erro": started, "reset": changed, "religado": was_active and not started}


def agent_status(directory: Path, key_file: Path = Path("/etc/quant/agent.env")) -> dict:
    """Estado do agente de IA para o painel: configuracao, ultimo ciclo, decisoes recentes e posicoes do livro dele."""
    from . import agent

    cfg = agent.load_config(directory / "config.json")
    state = agent.read_state(directory)
    pnl, _ = agent.trades_of_agent(Path(os.environ.get("QUANT_TRADES_LOG", "trades.csv")), time.time())
    return {"config": cfg, "state": state, "chave": key_file.exists(), "modelos": list(agent.MODELS),
            "pnl_hoje": round(pnl, 4), "livro": agent.read_book(directory),
            "decisoes": agent.read_decisions(directory / "decisions.jsonl", 30)}


ORDER_REQUEST = Path("/var/lib/quant/order-request.json")
ORDER_RESULT = Path("/var/lib/quant/order-result.json")
ORDER_UNIT = "quant-order.service"


def submit_order(body: object, req_path: Path, res_path: Path, run=None) -> tuple[int, dict]:
    """Valida o pedido da boleta manual, grava-o e dispara ``quant-order``. Nao fala com a corretora nem le chaves.
    ``open``/``stop`` exigem o runner parado (dois donos da mesma posicao); ``close`` e ``status`` sempre passam."""
    from .manual import OrderError, validate

    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=30))
    try:
        req = validate(body)
    except OrderError as e:
        return 400, {"ok": False, "erro": str(e)}
    if req["action"] in ("open", "stop") and run(["systemctl", "is-active", SERVICE]).stdout.strip() == "active":
        return 409, {"ok": False,
                     "erro": "pare o runner antes de operar a mao (Operar > Parar): ele e o outro dono da posicao"}
    if run(["systemctl", "is-active", ORDER_UNIT]).stdout.strip() in ("active", "activating"):
        return 409, {"ok": False, "erro": "ja ha uma ordem em andamento; aguarde"}
    req["id"] = f"{int(time.time() * 1000)}"
    tmp = req_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(req))
    tmp.replace(req_path)
    res_path.unlink(missing_ok=True)
    r = run(["systemctl", "start", "--no-block", ORDER_UNIT])
    if r.returncode:
        return 409, {"ok": False, "erro": (r.stderr or "").strip()[:300] or "nao consegui disparar a ordem"}
    return 202, {"ok": True, "id": req["id"]}


def read_order(res_path: Path) -> dict:
    try:
        return json.loads(res_path.read_text())
    except (OSError, ValueError):
        return {"pendente": True}


def runner_action(verb: str, kill_file: Path, run=None) -> dict:
    """start/stop/restart do servico do runner. Com KILL presente nao liga: retomar e decisao humana."""
    if verb not in VERBS:
        raise SettingError(f"acao invalida {verb!r}")
    if verb in ("start", "restart") and kill_file.exists():
        return {"ok": False, "erro": "arquivo KILL presente: revise a posicao e remova-o na VM antes de ligar"}
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=30))
    r = run(["systemctl", verb, SERVICE])
    return {"ok": r.returncode == 0, "erro": (r.stderr or "").strip()[:300] if r.returncode else ""}
# painel Angular (web/): `npm run build` gera web/dist/web/browser; na VM o pacote traz o build em /opt/quant/web-dist
WEB_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "web" / "dist" / "web" / "browser"
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".ico": "image/x-icon", ".svg": "image/svg+xml",
        ".png": "image/png", ".txt": "text/plain; charset=utf-8", ".map": "application/json"}
HASHED = re.compile(r"-[A-Za-z0-9_]{8}\.(js|css)$")  # arquivos com hash no nome podem ficar em cache para sempre
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
NO_BUILD = ("<!doctype html><meta charset=utf-8><title>quant</title><body style='font:15px system-ui;padding:2em'>"
            "<h1>Painel Angular não encontrado</h1><p>Rode <code>npm ci &amp;&amp; npm run build</code> em "
            "<code>web/</code> (ou envie o pacote com <code>deploy/enviar-pacote.sh</code>) e recarregue.</p>").encode()


def web_dir() -> Path:
    return Path(os.environ.get("QUANT_WEB_DIR", str(WEB_DIR_DEFAULT)))


def resolve_static(root: Path, url_path: str) -> tuple[Path | None, bool]:
    """(arquivo, e_rota_spa). Nunca sai de ``root``; sem extensao = rota do Angular, que cai no index.html."""
    rel = unquote(url_path).lstrip("/")
    if not rel:
        rel = "index.html"
    try:
        target = (root / rel).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            return None, False  # tentativa de sair da pasta (../)
    except (OSError, ValueError):
        return None, False
    if target.is_file():
        return target, False
    spa = "." not in Path(rel).name or rel == "index.html"  # sem build, '/' deve avisar (503) em vez de dar 404
    return ((root / "index.html"), True) if spa else (None, False)


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


def trades_summary(path: Path, n: int = 200) -> dict:
    """Historico de trades fechados do runner (CSV gravado por quant.live.runner): linhas, total, acerto, curva."""
    try:
        rows = list(csv.DictReader(path.read_text().splitlines()))
    except OSError:
        rows = []
    trades = []
    for r in rows:
        try:
            trades.append({"ts": r["ts"], "origem": r.get("origem", ""), "side": int(r["side"]), "qty": float(r["qty"]),
                           "entrada": float(r["entrada"]), "saida": float(r["saida"]), "pnl": float(r["pnl"]),
                           "motivo": r.get("motivo", "")})
        except (KeyError, ValueError):
            continue
    cum, curve = 0.0, []
    for t in trades:
        cum += t["pnl"]
        curve.append([t["ts"], round(cum, 6)])
    wins = sum(1 for t in trades if t["pnl"] > 0)
    peak, mdd = 0.0, 0.0
    for _, c in curve:
        peak = max(peak, c)
        mdd = min(mdd, c - peak)
    return {"count": len(trades), "pnl_total": round(cum, 6), "wins": wins,
            "win_rate": (wins / len(trades)) if trades else None, "max_dd": round(mdd, 6),
            "trades": trades[-n:][::-1], "curve": curve[-n:]}


def venues_status(key_exists=os.path.exists) -> dict:
    """O que o painel consegue afirmar sobre cada corretora (sem ler nenhuma chave)."""
    kalshi_key = "/etc/quant/kalshi-demo.key"
    return {"binance": {"modos": ["paper", "testnet"], "credencial": "em /etc/quant-live.env (o painel nao le)"},
            "kalshi": {"modos": ["paper", "testnet"], "credencial": "chave presente" if key_exists(kalshi_key)
                       else f"FALTA {kalshi_key}"},
            "polymarket": {"modos": [], "credencial": "so por edicao na VM (live, fora do Brasil/EUA)"}}


def deploy_status(status_path: Path, inbox: Path) -> dict:
    """Ultima atualizacao (escrita por deploy/atualizar.sh) e se ha pacote esperando na caixa de entrada."""
    st = read_state(status_path)
    pkg = None
    try:
        s = inbox.stat()
        pkg = {"bytes": s.st_size, "mtime": s.st_mtime}
    except OSError:
        pass
    return {"last": st, "pacote": pkg}


def alerts_status(env_path: Path, state_path: Path) -> dict:
    """Canais de alerta configurados (so os nomes; nunca o token) e quando o watcher rodou pela ultima vez."""
    from . import alerts

    st = read_state(state_path)
    try:
        mtime = state_path.stat().st_mtime
    except OSError:
        mtime = None
    return {"canais": alerts.channels(alerts.load_env(env_path)), "ultima_checagem": mtime, "estado": st}


def read_selfcheck(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


_KFEEDS: dict[str, object] = {}


def kalshi_closes(ticker: str, n: int = 120) -> list[list[float]]:
    """[[ts_ms, close], ...] das velas de 1 min da Kalshi (ativos sem par na Binance); [] se falhar. Feed em cache."""
    from .live.feed import KalshiFeed

    try:
        feed = _KFEEDS.get(ticker) or _KFEEDS.setdefault(ticker, KalshiFeed(ticker, "1m"))
        df = feed.closed_bars(n)  # type: ignore[attr-defined]
        return [[int(t.timestamp() * 1000), float(c)] for t, c in zip(df["datetime"], df["close"], strict=True)]
    except Exception:  # noqa: BLE001 - o painel nao pode cair porque a Kalshi demorou
        return []


def _bar_age(state: dict | None, now: float) -> int | None:
    if state and state.get("last_bar"):
        try:
            import pandas as pd
            return round(now - pd.Timestamp(state["last_bar"], tz="UTC").timestamp())
        except (ValueError, TypeError):
            return None
    return None


def assets_summary(state_dir: Path, names: list[str], now: float) -> list[dict]:
    """Uma linha por ativo do runner multi-ativo, lida dos ``live_state.<ATIVO>.json`` (sem falar com a corretora)."""
    out = []
    for a in names:
        st = read_state(state_dir / f"live_state.{a}.json")
        risk = (st or {}).get("risk") or {}
        ent = (st or {}).get("entry")
        out.append({"asset": a, "position": ent, "stop": (st or {}).get("stop"), "pnl": float(risk.get("pnl") or 0.0),
                    "trades": int(risk.get("trades") or 0), "halted": bool(risk.get("halted")),
                    "reason": risk.get("reason") or "", "last_bar_age_s": _bar_age(st, now), "started": st is not None})
    return out


def build_status(state_path: Path, kill_file: Path, *, now: float | None = None, asset: str | None = None) -> dict:
    now = time.time() if now is None else now
    from .live import assets as assets_mod

    cfg = runner_config()
    names = [a for a in cfg.get("QUANT_ASSETS", "").split(",") if a in assets_mod.CATALOG]
    if asset not in names:
        asset = names[0] if names else None
    state = read_state(state_path.parent / f"live_state.{asset}.json" if asset else state_path)
    last_bar_age = _bar_age(state, now)
    tf = cfg.get("QUANT_TIMEFRAME", "1m")
    if asset and not assets_mod.uses_binance(asset):
        bars = kalshi_closes(assets_mod.ticker(asset))
    else:
        bars = recent_closes(assets_mod.symbol(asset) if asset else cfg.get("QUANT_SYMBOL", "ETH/USDT:USDT"), tf)
    return {
        "now": now,
        "asset": asset,
        "assets": assets_summary(state_path.parent, names, now) if names else [],
        "bars": bars,
        "service": _run(["systemctl", "is-active", SERVICE]) or "desconhecido",
        "kill_file": kill_file.exists(),
        "config": cfg,
        "health": service_health(now=now),
        "selfcheck": read_selfcheck(Path(os.environ.get("QUANT_SELFCHECK", "selfcheck.json"))),
        "deploy": deploy_status(Path(os.environ.get("QUANT_DEPLOY_STATUS", "deploy.json")),
                                Path(os.environ.get("QUANT_INBOX", "/var/lib/quant/inbox/quant.tar.gz"))),
        "alerts": alerts_status(Path(os.environ.get("QUANT_ALERT_ENV", "/etc/quant/alert.env")),
                                Path(os.environ.get("QUANT_ALERT_STATE", "alerts_state.json"))),
        "trades": trades_summary(Path(os.environ.get("QUANT_TRADES_LOG", "trades.csv")), 30),
        "venues": venues_status(),
        "portfolio": portfolio_summary(Path(os.environ.get("QUANT_PORT_LOG", "portfolio_log.csv"))),
        "state": state,
        "last_bar_age_s": last_bar_age,
        "log": _run(["journalctl", "-u", SERVICE, "-n", "40", "--no-pager", "-o", "short-iso"]).splitlines()[-40:],
    }


def trigger_kill(kill_file: Path) -> bool:
    kill_file.parent.mkdir(parents=True, exist_ok=True)
    kill_file.write_text(f"kill via painel em {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n")
    return kill_file.exists()


def make_handler(state_path: Path, kill_file: Path, runtime_path: Path = RUNTIME_ENV, run=None, auth=None):
    """``auth`` (quant.auth.Auth) liga contas e papeis: cada rota /api/* exige a sessao e o papel de
    ``accounts.required_role`` (401 sem sessao, 403 sem papel). ``None`` = sem login (so testes e `ng serve` local)."""
    from . import accounts
    from . import auth as authmod

    cookie_path = os.environ.get("QUANT_COOKIE_PATH", "/")

    class Handler(BaseHTTPRequestHandler):
        server_version = "quant-control"
        sys_version = ""

        def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store", extra=()) -> None:
            self.send_response(code)
            for k, v in extra:
                self.send_header(k, v)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            if ctype.startswith("text/html"):
                self.send_header("Content-Security-Policy", CSP)
                self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict, extra=()) -> None:
            self._send(code, json.dumps(obj, default=str).encode(), "application/json; charset=utf-8", extra=extra)

        def _ip(self) -> str:
            peer = self.client_address[0]
            return (self.headers.get("X-Real-IP") or peer) if peer in ("127.0.0.1", "::1") else peer  # so o nginx local

        def _session(self) -> dict | None:
            if auth is None:
                return {"sid": "dev", "id": "dev", "user": "dev", "role": "admin", "disabled": False, "totp": False}
            return auth.session(self.headers.get("Cookie"))

        def _gate(self, method: str, path: str):
            """(sessao, liberado). Ja responde 401/403 quando nao liberado. Rotas publicas passam com sessao ou None."""
            need = accounts.required_role(method, path)
            sess = self._session()
            if need is None:
                return sess, True
            if sess is None:
                self._json(401, {"erro": "login necessario", "setup": bool(auth and auth.needs_setup)})
                return None, False
            if not accounts.allowed(sess["role"], need):
                self._json(403, {"erro": f"seu papel ({sess['role']}) nao pode fazer isso"})
                return sess, False
            return sess, True

        def _account(self, method: str, path: str, sess, body: dict):
            """Roda a rota de conta e responde. True se era uma rota de conta."""
            if auth is None:
                return False
            res = accounts.handle(auth, method, path, sess, body, ip=self._ip(),
                                  agent=self.headers.get("User-Agent", ""), cookie_header=self.headers.get("Cookie"))
            if res is None:
                return False
            code, obj, cookie = res
            extra = []
            if cookie and cookie[0] == "set":
                extra = self._set_cookie(cookie[1], cookie[2])
            elif cookie:
                extra = self._set_cookie("", 0)
            self._json(code, obj, extra)
            return True

        def _body(self, limit: int = 2048):
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), limit)) or b"{}")
            except ValueError:
                return None
            return body if isinstance(body, dict) else None

        def _set_cookie(self, value: str, ttl: int):
            secure = self.headers.get("X-Forwarded-Proto") == "https"
            return [("Set-Cookie", authmod.cookie_header(value, ttl, path=cookie_path, secure=secure))]

        def _static(self, path: str) -> None:
            root = web_dir()
            f, spa = resolve_static(root, path)
            if f is None:
                return self._json(404, {"erro": "nao encontrado"})
            try:
                body = f.read_bytes()
            except OSError:
                return self._send(503, NO_BUILD, "text/html; charset=utf-8")
            cache = "public, max-age=31536000, immutable" if HASHED.search(f.name) else "no-store"
            self._send(200, body, MIME.get(f.suffix.lower(), "application/octet-stream"), cache)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if not path.startswith("/api/"):
                return self._static(path)
            sess, ok = self._gate("GET", path)
            if not ok:
                return
            if self._account("GET", path, sess, {}):
                return
            if path == "/api/status":
                q = parse_qs(urlsplit(self.path).query)
                self._json(200, build_status(state_path, kill_file, asset=(q.get("asset") or [None])[0]))
            elif path == "/api/trades":
                self._json(200, trades_summary(Path(os.environ.get("QUANT_TRADES_LOG", "trades.csv")), 500))
            elif path == "/api/trades.csv":
                try:
                    body = Path(os.environ.get("QUANT_TRADES_LOG", "trades.csv")).read_bytes()
                except OSError:
                    body = b""
                self._send(200, body, "text/csv; charset=utf-8")
            elif path == "/api/agent":
                self._json(200, agent_status(Path(os.environ.get("QUANT_AGENT_DIR", "/var/lib/quant/agent")),
                                             Path(os.environ.get("QUANT_AGENT_ENV", "/etc/quant/agent.env"))))
            elif path == "/api/markets":
                from .live import assets as assets_mod

                self._json(200, {"markets": assets_mod.rows(), "binance": list(assets_mod.CRYPTO)})
            elif path == "/api/order":
                self._json(200, read_order(Path(os.environ.get("QUANT_ORDER_RESULT", str(ORDER_RESULT)))))
            elif path == "/api/settings":
                self._json(200, {"saved": read_runtime(runtime_path), "effective": runner_config(),
                                 "options": {"QUANT_MODE": ["paper", "testnet"], "QUANT_VENUE": ["binance", "kalshi"],
                                             "QUANT_TIMEFRAME": ["1m", "5m", "15m", "1h"],
                                             "QUANT_DIRECTION": ["both", "long"]}})
            else:
                self._json(404, {"erro": "nao encontrado"})

        def do_POST(self):  # noqa: N802
            # o navegador manda a senha do nginx sozinho: o cabecalho proprio barra CSRF (so JS da mesma origem)
            if self.headers.get("X-Quant-Control") != "1":
                return self._json(403, {"erro": "cabecalho X-Quant-Control ausente"})
            path = self.path.split("?")[0]
            sess, ok = self._gate("POST", path)
            if not ok:
                return
            body = self._body(4096)
            if body is None:
                return self._json(400, {"ok": False, "erro": "corpo JSON invalido"})
            if self._account("POST", path, sess, body):
                return
            if auth is not None and sess:  # trilha de auditoria das acoes de operacao
                auth.audit("acao", sess["user"], self._ip(), f"{path} {self._summary(path, body)}")
            if path == "/api/kill":
                ok = trigger_kill(kill_file)
                return self._json(200 if ok else 500, {"kill_file": ok})
            units = {"/api/selfcheck/run": "quant-selfcheck.service", "/api/deploy/run": "quant-deploy.service",
                     "/api/deploy/rollback": "quant-rollback.service"}
            if path in units:
                run_ = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=30))
                r = run_(["systemctl", "start", "--no-block", units[path]])
                ok = r.returncode == 0
                return self._json(200 if ok else 409, {"ok": ok, "erro": "" if ok else (r.stderr or "").strip()[:300]})
            if path == "/api/alerts/test":
                from . import alerts

                cfg = alerts.load_env(Path(os.environ.get("QUANT_ALERT_ENV", "/etc/quant/alert.env")))
                if not alerts.channels(cfg):
                    return self._json(409, {"ok": False, "erro": "nenhum canal configurado em /etc/quant/alert.env"})
                sent = alerts.deliver(cfg, "Alerta de teste enviado pelo painel de controle.")
                return self._json(200 if sent else 502, {"ok": bool(sent), "canais": sent,
                                                         "erro": "" if sent else "falha ao entregar (veja o journal)"})
            if path == "/api/order":
                code, res = submit_order(body, Path(os.environ.get("QUANT_ORDER_REQUEST", str(ORDER_REQUEST))),
                                         Path(os.environ.get("QUANT_ORDER_RESULT", str(ORDER_RESULT))), run)
                return self._json(code, res)
            if path.startswith("/api/agent/"):
                return self._agent_post(path, body, sess)
            if path == "/api/risk/reset":
                res = reset_risk(state_path, kill_file, run)
                return self._json(200 if res["ok"] else 409, res)
            if path.startswith("/api/runner/"):
                try:
                    res = runner_action(path.rsplit("/", 1)[1], kill_file, run)
                except SettingError as e:
                    return self._json(404, {"ok": False, "erro": str(e)})
                return self._json(200 if res["ok"] else 409, res)
            if path == "/api/settings":
                try:
                    return self._json(200, {"saved": write_runtime(runtime_path, body), "restart_needed": True})
                except (SettingError, ValueError) as e:
                    return self._json(400, {"erro": str(e)})
            self._json(404, {"erro": "nao encontrado"})

        def _agent_post(self, path: str, body: dict, sess):
            from . import agent

            directory = Path(os.environ.get("QUANT_AGENT_DIR", "/var/lib/quant/agent"))
            verb = path.rsplit("/", 1)[1]
            try:
                if verb == "toggle":  # ligar/desligar: operador; so a chave enabled
                    if set(body) != {"enabled"}:
                        raise agent.ConfigError("toggle aceita so 'enabled'")
                    return self._json(200, {"ok": True, "config": agent.save_config(directory / "config.json", body)})
                if verb == "config":  # limites, modelo, universo: so admin
                    if sess is not None and sess.get("role") != "admin":
                        return self._json(403, {"ok": False, "erro": "so administrador muda os limites do agente"})
                    return self._json(200, {"ok": True, "config": agent.save_config(directory / "config.json", body)})
                if verb == "run":  # roda um ciclo agora (ignora o intervalo)
                    run_ = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=30))
                    r = run_(["systemctl", "start", "--no-block", "quant-agent-agora.service"])
                    ok = r.returncode == 0
                    err = "" if ok else (r.stderr or "").strip()[:300]
                    return self._json(200 if ok else 409, {"ok": ok, "erro": err})
            except agent.ConfigError as e:
                return self._json(400, {"ok": False, "erro": str(e)})
            return self._json(404, {"ok": False, "erro": "nao encontrado"})

        @staticmethod
        def _summary(path: str, body: dict) -> str:
            if path == "/api/order":
                return " ".join(f"{k}={body[k]}" for k in ("action", "side", "qty", "stop_pct") if k in body)
            if path == "/api/settings":
                return ",".join(sorted(str(k) for k in body))
            return ""

        def log_message(self, fmt, *args):  # noqa: A002
            print(f"{self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    state = Path(os.environ.get("QUANT_STATE", "live_state.json"))
    kill = Path(os.environ.get("QUANT_KILL_FILE", "KILL"))
    port = int(os.environ.get("QUANT_CONTROL_PORT", "8765"))
    runtime = Path(os.environ.get("QUANT_RUNTIME_ENV", str(RUNTIME_ENV)))
    from .auth import Auth

    auth = None if os.environ.get("QUANT_AUTH_DISABLED") == "1" else Auth.from_env()
    if auth is not None and auth.needs_setup:
        print("PRIMEIRO ACESSO: nenhum usuario ainda; o primeiro a abrir o painel cria o admin.", flush=True)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, kill, runtime, auth=auth))
    print(f"quant.control em 127.0.0.1:{port} (estado={state}, kill={kill}, login={'off' if auth is None else 'on'})",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
