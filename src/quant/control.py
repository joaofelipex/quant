"""Painel de controle do runner ao vivo: estado em tempo real e kill-switch, atras do nginx (HTTPS + senha).

    QUANT_STATE=/var/lib/quant/live_state.json QUANT_KILL_FILE=/var/lib/quant/KILL python -m quant.control

Escuta so em 127.0.0.1 (o nginx faz proxy em /controle/). Biblioteca padrao apenas. O que ele PODE fazer: ler o estado
do runner, ler o journal e criar o arquivo KILL. O que NAO faz, de proposito: ligar o runner, enviar ordem, mudar
parametro, apagar o KILL (retomar depois de um kill e decisao humana, ver deploy/README.md) ou ler chaves.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVICE = "quant-live"
ENV_WHITELIST = ("QUANT_MODE", "QUANT_SYMBOL", "QUANT_TIMEFRAME", "QUANT_QTY", "QUANT_MAX_DAILY_LOSS",
                 "QUANT_STOP_ATR", "QUANT_TESTNET_KIND")
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
    return {
        "now": now,
        "service": _run(["systemctl", "is-active", SERVICE]) or "desconhecido",
        "kill_file": kill_file.exists(),
        "config": runner_config(),
        "state": state,
        "last_bar_age_s": last_bar_age,
        "log": _run(["journalctl", "-u", SERVICE, "-n", "40", "--no-pager", "-o", "short-iso"]).splitlines()[-40:],
    }


def trigger_kill(kill_file: Path) -> bool:
    kill_file.parent.mkdir(parents=True, exist_ok=True)
    kill_file.write_text(f"kill via painel em {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n")
    return kill_file.exists()


def make_handler(state_path: Path, kill_file: Path):
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
            else:
                self._json(404, {"erro": "nao encontrado"})

        def do_POST(self):  # noqa: N802
            # o navegador manda a senha do nginx sozinho: o cabecalho proprio barra CSRF (so JS da mesma origem)
            if self.headers.get("X-Quant-Control") != "1":
                return self._json(403, {"erro": "cabecalho X-Quant-Control ausente"})
            if self.path.split("?")[0] == "/api/kill":
                ok = trigger_kill(kill_file)
                return self._json(200 if ok else 500, {"kill_file": ok})
            self._json(404, {"erro": "nao encontrado"})

        def log_message(self, fmt, *args):  # noqa: A002
            print(f"{self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    state = Path(os.environ.get("QUANT_STATE", "live_state.json"))
    kill = Path(os.environ.get("QUANT_KILL_FILE", "KILL"))
    port = int(os.environ.get("QUANT_CONTROL_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, kill))
    print(f"quant.control em 127.0.0.1:{port} (estado={state}, kill={kill})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
