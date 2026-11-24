"""Painel de controle: so le estado e cria KILL; escrita exige cabecalho proprio (CSRF); nada de chaves."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from quant import control


@pytest.fixture
def server(tmp_path):
    state, kill = tmp_path / "live_state.json", tmp_path / "KILL"
    state.write_text(json.dumps({"last_bar": "2026-01-01 00:00:00", "stop": None, "entry": None,
                                 "risk": {"halted": False, "pnl": 0.0, "trades": 0}, "executor": {"pos": None}}))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(state, kill))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", kill
    srv.shutdown()


def call(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_status_devolve_estado_do_runner(server):
    base, kill = server
    code, body = call(base + "/api/status")
    d = json.loads(body)
    assert code == 200 and d["state"]["last_bar"] == "2026-01-01 00:00:00"
    assert d["kill_file"] is False and d["last_bar_age_s"] > 0


def test_pagina_inicial_e_servida(server):
    code, body = call(server[0] + "/")
    assert code == 200 and b"kill-switch" in body.lower()


def test_kill_sem_cabecalho_e_recusado(server):
    base, kill = server
    code, _ = call(base + "/api/kill", "POST")
    assert code == 403 and not kill.exists()


def test_kill_com_cabecalho_cria_o_arquivo(server):
    base, kill = server
    code, body = call(base + "/api/kill", "POST", {"X-Quant-Control": "1"})
    assert code == 200 and kill.exists() and json.loads(body)["kill_file"] is True
    assert json.loads(call(base + "/api/status")[1])["kill_file"] is True


def test_get_nao_aciona_o_kill_e_rotas_desconhecidas_dao_404(server):
    base, kill = server
    assert call(base + "/api/kill")[0] == 404 and not kill.exists()
    assert call(base + "/api/outro", "POST", {"X-Quant-Control": "1"})[0] == 404


def test_config_so_expoe_chaves_da_whitelist(monkeypatch, tmp_path):
    env = tmp_path / "environ"
    env.write_bytes(b"QUANT_MODE=paper\0BINANCE_API_SECRET=segredo\0QUANT_SYMBOL=ETH/USDT:USDT\0PATH=/bin\0")
    real = Path
    monkeypatch.setattr(control, "Path", lambda p: env if str(p).startswith("/proc/") else real(p))
    assert control.runner_config("123") == {"QUANT_MODE": "paper", "QUANT_SYMBOL": "ETH/USDT:USDT"}


def test_unit_e_nginx_do_controle():
    root = Path(__file__).resolve().parents[1] / "deploy"
    unit = (root / "quant-control.service").read_text()
    assert "EnvironmentFile" not in unit.replace("# NAO le", "")  # nunca le o env com as chaves
    assert "quant-live.env" not in "\n".join(ln for ln in unit.splitlines() if not ln.startswith("#"))
    ng = (root / "nginx-quant.conf").read_text()
    https = ng.split("listen 443")[1]
    assert "location /controle/" in https and "proxy_pass http://127.0.0.1:8765/" in https
    assert "controle" not in ng.split("listen 443")[0]  # nada de controle na porta 80


def test_barras_recentes_falham_para_lista_vazia(monkeypatch):
    def boom(*a, **k):
        raise OSError("sem rede")
    monkeypatch.setattr(control.urllib.request, "urlopen", boom)
    control._BARS_CACHE.update({"t": 0.0, "key": None, "data": []})
    assert control.recent_closes("ETH/USDT:USDT", "1m", now=1000.0) == []


def test_resumo_do_paper_da_carteira(tmp_path):
    log = tmp_path / "p.csv"
    log.write_text("date,equity,pnl,funding,cost,turnover,gross,w_BTCUSDT,w_ETHUSDT\n"
                   "2026-11-23,1.0,0.0,0,0,0,0.3,-0.07,-0.05\n2026-11-24,0.99,-0.01,nan,0,0,0.3,-0.07,0.02\n")
    s = control.portfolio_summary(log)
    assert s["days"] == 2 and s["equity"] == 0.99 and s["pnl"] == -0.01
    assert s["weights"] == {"BTCUSDT": -0.07, "ETHUSDT": 0.02} and s["series"][0] == ["2026-11-23", 1.0]
    assert control.portfolio_summary(tmp_path / "nao_existe.csv") is None


def test_saude_sem_systemctl_nao_quebra(monkeypatch):
    monkeypatch.setattr(control, "_run", lambda *a, **k: "")
    assert control.service_health() == {"uptime_s": None, "restarts": None, "memory_mb": None}
