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
def server(tmp_path, monkeypatch):
    # isola do host: na VM o runner real (mesmo usuario) tem QUANT_ASSETS no ambiente e mudaria o que o status le
    monkeypatch.setattr(control, "runner_config", lambda *a: {})
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


def test_pagina_inicial_sem_build_avisa_em_vez_de_quebrar(server, monkeypatch, tmp_path):
    monkeypatch.setenv("QUANT_WEB_DIR", str(tmp_path / "nao_existe"))
    code, body = call(server[0] + "/")
    assert code == 503 and b"npm" in body


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


class FakeRun:
    def __init__(self, rc=0, err=""):
        self.calls, self.rc, self.err = [], rc, err

    def __call__(self, cmd):
        self.calls.append(cmd)
        return type("R", (), {"returncode": self.rc, "stderr": self.err})()


@pytest.fixture
def ctl(tmp_path):
    state, kill, rt, run = tmp_path / "s.json", tmp_path / "KILL", tmp_path / "runtime.env", FakeRun()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(state, kill, rt, run))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", kill, rt, run
    srv.shutdown()


H = {"X-Quant-Control": "1"}


def post(url, body=None, headers=H):
    req = urllib.request.Request(url, method="POST", headers={**(headers or {}), "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else b"")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_acoes_do_runner_chamam_so_o_systemctl_da_unit(ctl):
    base, kill, rt, run = ctl
    for verb in ("start", "stop", "restart"):
        assert post(f"{base}/api/runner/{verb}")[0] == 200
    assert run.calls == [["systemctl", v, "quant-live"] for v in ("start", "stop", "restart")]
    assert post(f"{base}/api/runner/enable")[0] == 404 and len(run.calls) == 3


def test_acoes_exigem_o_cabecalho_anti_csrf(ctl):
    base, kill, rt, run = ctl
    assert post(f"{base}/api/runner/stop", headers={})[0] == 403 and not run.calls
    assert post(f"{base}/api/settings", {"QUANT_QTY": "0.5"}, headers={})[0] == 403 and not rt.exists()


def test_com_kill_nao_liga_mas_para(ctl):
    base, kill, rt, run = ctl
    kill.write_text("x")
    code, body = post(f"{base}/api/runner/start")
    assert code == 409 and "KILL" in body["erro"] and not run.calls
    assert post(f"{base}/api/runner/restart")[0] == 409
    assert post(f"{base}/api/runner/stop")[0] == 200


def test_falha_do_systemctl_vira_409_com_motivo(ctl):
    base, kill, rt, run = ctl
    run.rc, run.err = 1, "Access denied"
    code, body = post(f"{base}/api/runner/start")
    assert code == 409 and body["erro"] == "Access denied"


def test_parametros_validados_e_gravados_sem_segredos(ctl):
    base, kill, rt, run = ctl
    code, body = post(f"{base}/api/settings", {"QUANT_MODE": "testnet", "QUANT_QTY": "0.02", "QUANT_TIMEFRAME": "5m"})
    assert code == 200 and body["restart_needed"] is True
    assert control.read_runtime(rt) == {"QUANT_MODE": "testnet", "QUANT_QTY": "0.02", "QUANT_TIMEFRAME": "5m"}
    assert json.loads(call(f"{base}/api/settings")[1])["saved"]["QUANT_QTY"] == "0.02"


@pytest.mark.parametrize("body", [
    {"QUANT_MODE": "live"},                      # live nunca pelo navegador
    {"QUANT_VENUE": "polymarket"},               # sem testnet: so por edicao na VM
    {"BINANCE_API_SECRET": "x"},                 # chaves nunca
    {"QUANT_QTY": "10"}, {"QUANT_QTY": "0"}, {"QUANT_QTY": "abc"}, {"QUANT_QTY": "nan"},
    {"QUANT_MAX_DAILY_LOSS": "-5"}, {"QUANT_STOP_ATR": "99"}, {"QUANT_TIMEFRAME": "1s"},
    {"QUANT_ALLOW_MAINNET": "yes-i-know"}, [1, 2],
])
def test_parametros_invalidos_sao_recusados_sem_gravar(ctl, body):
    base, kill, rt, run = ctl
    code, _ = post(f"{base}/api/settings", body)
    assert code == 400 and not rt.exists()


def test_atualizacao_parcial_preserva_os_outros_parametros(tmp_path):
    rt = tmp_path / "r.env"
    control.write_runtime(rt, {"QUANT_QTY": "0.05", "QUANT_MODE": "paper"})
    control.write_runtime(rt, {"QUANT_QTY": "0.01"})
    assert control.read_runtime(rt) == {"QUANT_QTY": "0.01", "QUANT_MODE": "paper"}


def test_polkit_so_libera_a_unit_do_runner_e_as_tres_acoes():
    root = Path(__file__).resolve().parents[1] / "deploy"
    rule = (root / "50-quant-control.rules").read_text()
    assert 'subject.user !== "quant"' in rule and 'unit === "quant-live.service"' in rule
    assert '["start", "stop", "restart"]' in rule and "manage-unit-files" not in rule
    live = (root / "quant-live.service").read_text()
    assert live.index("EnvironmentFile=/etc/quant-live.env") < live.index("EnvironmentFile=-/var/lib/quant/runtime.env")
    ctl_unit = (root / "quant-control.service").read_text()
    assert "runtime.env" in ctl_unit and "QUANT_SELFCHECK=/var/lib/quant/selfcheck.json" in ctl_unit


def make_web(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><app-root></app-root>")
    (web / "main-ABCD1234.js").write_text("console.log(1)")
    (web / "styles.css").write_text("a{}")
    (tmp_path / "segredo.txt").write_text("nao pode vazar")
    return web


def test_spa_serve_index_assets_e_rotas_do_angular(server, monkeypatch, tmp_path):
    monkeypatch.setenv("QUANT_WEB_DIR", str(make_web(tmp_path)))
    base = server[0]
    for route in ("/", "/index.html", "/trades", "/gestao"):  # rotas do Angular caem no index.html
        code, body = call(base + route)
        assert code == 200 and b"app-root" in body, route
    req = urllib.request.urlopen(base + "/main-ABCD1234.js")
    assert req.headers["Content-Type"].startswith("text/javascript")
    assert "immutable" in req.headers["Cache-Control"]  # arquivo com hash
    assert urllib.request.urlopen(base + "/styles.css").headers["Cache-Control"] == "no-store"
    index = urllib.request.urlopen(base + "/")
    csp = index.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert call(base + "/nao-existe.js")[0] == 404  # arquivo com extensao que nao existe nao vira index


@pytest.mark.parametrize("evil", ["/../segredo.txt", "/%2e%2e/segredo.txt", "/..%2fsegredo.txt",
                                  "/web/../../segredo.txt"])
def test_servidor_estatico_nao_sai_da_pasta(server, monkeypatch, tmp_path, evil):
    monkeypatch.setenv("QUANT_WEB_DIR", str(make_web(tmp_path)))
    code, body = call(server[0] + evil)
    assert b"nao pode vazar" not in body


def test_api_nao_cai_no_fallback_da_spa(server, monkeypatch, tmp_path):
    monkeypatch.setenv("QUANT_WEB_DIR", str(make_web(tmp_path)))
    code, body = call(server[0] + "/api/inexistente")
    assert code == 404 and b"app-root" not in body


def test_selfcheck_aparece_no_status_e_pode_ser_disparado(ctl, tmp_path, monkeypatch):
    base, kill, rt, run = ctl
    report = tmp_path / "sc.json"
    report.write_text(json.dumps({"ok": True, "at": "2026-11-24T00:00:00+00:00", "tests": None, "checks": [],
                                  "paper": None}))
    monkeypatch.setenv("QUANT_SELFCHECK", str(report))
    assert json.loads(call(base + "/api/status")[1])["selfcheck"]["ok"] is True
    assert post(f"{base}/api/selfcheck/run", headers={})[0] == 403
    assert post(f"{base}/api/selfcheck/run")[0] == 200
    assert run.calls[-1] == ["systemctl", "start", "--no-block", "quant-selfcheck.service"]
    monkeypatch.setenv("QUANT_SELFCHECK", str(tmp_path / "nao.json"))
    assert json.loads(call(base + "/api/status")[1])["selfcheck"] is None


def test_polkit_inclui_selfcheck_so_com_start():
    rule = (Path(__file__).resolve().parents[1] / "deploy" / "50-quant-control.rules").read_text()
    assert '"quant-selfcheck.service"' in rule and 'verb === "start"' in rule
    timer = (Path(__file__).resolve().parents[1] / "deploy" / "quant-selfcheck.timer").read_text()
    svc = (Path(__file__).resolve().parents[1] / "deploy" / "quant-selfcheck.service").read_text()
    assert "OnCalendar" in timer and "quant-live.env" not in "\n".join(
        ln for ln in svc.splitlines() if not ln.startswith("#"))


def test_trailing_e_filtro_de_fluxo_aceitam_zero_para_desligar(tmp_path):
    p = tmp_path / "runtime.env"
    got = control.write_runtime(p, {"QUANT_TRAIL_ATR": "0", "QUANT_FLOW_MIN": "0"})
    assert got["QUANT_TRAIL_ATR"] == "0" and got["QUANT_FLOW_MIN"] == "0"
    with pytest.raises(control.SettingError):
        control.write_runtime(p, {"QUANT_STOP_ATR": "0"})
