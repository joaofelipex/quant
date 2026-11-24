"""Gestao da VM: historico de trades, alertas e atualizacao de codigo pelo painel."""
import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import pytest
from test_live import FakeFeed, PaperExecutor, sig_fn

from quant import alerts, control
from quant.live.risk import RiskLimits, RiskManager
from quant.live.runner import Runner

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def make_runner(tmp_path, trades_path):
    bars = pd.DataFrame({"datetime": pd.date_range("2026-01-01", periods=5, freq="5min"), "open": 100.0, "high": 101.0,
                         "low": 99.0, "close": 100.0, "volume": 1.0})
    return Runner(FakeFeed(bars), PaperExecutor(), RiskManager(RiskLimits(max_qty=1, max_daily_loss=100)), sig_fn,
                  qty=0.1, timeframe="5m", state_path=tmp_path / "s.json", kill_file=tmp_path / "KILL",
                  trades_path=trades_path, label="kalshi/testnet")


# ---- historico de trades -------------------------------------------------------------------------------------
def test_runner_grava_o_trade_fechado_no_csv(tmp_path):
    log = tmp_path / "t.csv"
    r = make_runner(tmp_path, log)
    r._record_trade(pd.Timestamp("2026-01-01 00:10"), 1, 0.1, 100.0, 101.5, 0.15, "sinal oposto")
    rows = log.read_text().splitlines()
    assert rows[0].startswith("ts,origem,side,qty,entrada,saida,pnl,motivo")
    assert "kalshi/testnet,1,0.100000,100.0000,101.5000,0.1500,sinal oposto" in rows[1]


def test_falha_ao_gravar_o_historico_nao_derruba_o_runner(tmp_path):
    r = make_runner(tmp_path, tmp_path / "nao_existe" / "t.csv")
    r._record_trade(pd.Timestamp("2026-01-01"), 1, 0.1, 100.0, 101.0, 0.1, "x")  # nao levanta


def test_resumo_de_trades(tmp_path):
    f = tmp_path / "t.csv"
    f.write_text("ts,origem,side,qty,entrada,saida,pnl,motivo\n"
                 "2026-01-01 00:00:00,a,1,0.1,100,101,0.10,x\n"
                 "2026-01-01 01:00:00,a,-1,0.1,100,102,-0.20,stop\n"
                 "lixo,sem,campos\n"
                 "2026-01-01 02:00:00,a,1,0.1,100,103,0.30,x\n")
    s = control.trades_summary(f)
    assert s["count"] == 3 and s["wins"] == 2 and s["pnl_total"] == pytest.approx(0.2)
    assert s["max_dd"] == pytest.approx(-0.2) and s["trades"][0]["pnl"] == 0.3  # mais recente primeiro
    assert control.trades_summary(tmp_path / "nao.csv")["count"] == 0


# ---- alertas ---------------------------------------------------------------------------------------------------
def snap(**kw):
    base = {"runner": "active", "kill": False, "halted": False, "halt_reason": "", "selfcheck_ok": True, "n_trades": 0}
    return {**base, **kw}


def test_primeira_execucao_nao_alerta_so_registra():
    assert alerts.diff_events(snap(), None) == []


def test_so_avisa_quando_algo_muda():
    prev = snap()
    assert alerts.diff_events(snap(), prev) == []
    assert "FALHOU" in alerts.diff_events(snap(runner="failed"), prev)[0]
    assert "parou" in alerts.diff_events(snap(runner="inactive"), prev)[0]
    assert "ligou" in alerts.diff_events(snap(), snap(runner="inactive"))[0]
    assert "KILL" in alerts.diff_events(snap(kill=True), prev)[0]
    assert "TRAVA DE RISCO: perda" in alerts.diff_events(snap(halted=True, halt_reason="perda"), prev)[0]
    assert alerts.diff_events(snap(halted=True), snap(halted=True)) == []  # ja estava travado: nao repete
    assert "FALHOU" in alerts.diff_events(snap(selfcheck_ok=False), prev)[0]
    assert "normal" in alerts.diff_events(snap(), snap(selfcheck_ok=False))[0]
    t = [{"side": "1", "entrada": "100", "saida": "101", "pnl": "0.1", "motivo": "stop", "origem": "k"}]
    assert "Trade fechado" in alerts.diff_events(snap(n_trades=1), prev, t)[0]


def test_canais_e_entrega_isolam_falhas():
    assert alerts.channels({}) == []
    cfg = {"QUANT_ALERT_TELEGRAM_TOKEN": "t", "QUANT_ALERT_TELEGRAM_CHAT": "c", "QUANT_ALERT_SMTP_HOST": "h",
           "QUANT_ALERT_SMTP_FROM": "a@b", "QUANT_ALERT_SMTP_TO": "c@d"}
    assert alerts.channels(cfg) == ["telegram", "email"]
    sent = []

    def boom(*a):
        raise OSError("rede")

    ok = alerts.deliver(cfg, "oi", tg=boom, mail=lambda c, t: sent.append(t))
    assert ok == ["email"] and sent == ["oi"]  # telegram caiu, e-mail seguiu


def test_run_once_nao_avanca_o_estado_se_nao_entregou(tmp_path):
    env, state, trades = tmp_path / "alert.env", tmp_path / "st.json", tmp_path / "t.csv"
    env.write_text("QUANT_ALERT_TELEGRAM_TOKEN=t\nQUANT_ALERT_TELEGRAM_CHAT=c\n")
    state.write_text(json.dumps(snap()))
    trades.write_text("ts,origem,side,qty,entrada,saida,pnl,motivo\n")
    ev = alerts.run_once(env, state, snap=snap(runner="failed"), trades_path=trades, deliver_fn=lambda c, t: [])
    assert len(ev) == 1 and json.loads(state.read_text())["runner"] == "active"  # tenta de novo no proximo minuto
    alerts.run_once(env, state, snap=snap(runner="failed"), trades_path=trades, deliver_fn=lambda c, t: ["telegram"])
    assert json.loads(state.read_text())["runner"] == "failed"


def test_run_once_manda_so_os_trades_novos(tmp_path):
    env, state, trades = tmp_path / "alert.env", tmp_path / "st.json", tmp_path / "t.csv"
    env.write_text("QUANT_ALERT_TELEGRAM_TOKEN=t\nQUANT_ALERT_TELEGRAM_CHAT=c\n")
    trades.write_text("ts,origem,side,qty,entrada,saida,pnl,motivo\n"
                      "a,x,1,0.1,100,101,0.1,m1\n"
                      "b,x,-1,0.1,100,99,0.1,m2\n")
    state.write_text(json.dumps(snap(n_trades=1)))
    msgs = []
    alerts.run_once(env, state, snap=snap(n_trades=2), trades_path=trades,
                    deliver_fn=lambda c, t: msgs.append(t) or ["telegram"])
    assert len(msgs) == 1 and "m2" in msgs[0] and "m1" not in msgs[0]


def test_segredo_do_alerta_nao_aparece_no_status(tmp_path):
    env = tmp_path / "alert.env"
    env.write_text("QUANT_ALERT_TELEGRAM_TOKEN=SEGREDO123\nQUANT_ALERT_TELEGRAM_CHAT=42\n")
    out = json.dumps(control.alerts_status(env, tmp_path / "x.json"))
    assert "SEGREDO123" not in out and "telegram" in out


# ---- painel: endpoints novos -----------------------------------------------------------------------------------
class FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        return type("R", (), {"returncode": 0, "stderr": ""})()


@pytest.fixture
def ctl(tmp_path, monkeypatch):
    run = FakeRun()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(tmp_path / "s.json", tmp_path / "KILL",
                                                                      tmp_path / "rt.env", run))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", run, monkeypatch, tmp_path
    srv.shutdown()


def post(url, headers=None):
    req = urllib.request.Request(url, method="POST", headers=headers or {}, data=b"")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


H = {"X-Quant-Control": "1"}


def test_deploy_e_rollback_so_disparam_a_unit_certa_e_pedem_cabecalho(ctl):
    base, run, mp, tmp = ctl
    assert post(base + "/api/deploy/run")[0] == 403 and not run.calls
    assert post(base + "/api/deploy/run", H)[0] == 200
    assert post(base + "/api/deploy/rollback", H)[0] == 200
    assert [c[-1] for c in run.calls] == ["quant-deploy.service", "quant-rollback.service"]


def test_alerta_de_teste_sem_canal_da_409_e_com_canal_entrega(ctl):
    base, run, mp, tmp = ctl
    mp.setenv("QUANT_ALERT_ENV", str(tmp / "nao.env"))
    assert post(base + "/api/alerts/test", H)[0] == 409
    env = tmp / "a.env"
    env.write_text("QUANT_ALERT_TELEGRAM_TOKEN=t\nQUANT_ALERT_TELEGRAM_CHAT=c\n")
    mp.setenv("QUANT_ALERT_ENV", str(env))
    got = []
    mp.setattr(alerts, "send_telegram", lambda *a: got.append(a))
    code, body = post(base + "/api/alerts/test", H)
    assert code == 200 and body["canais"] == ["telegram"] and got


def test_status_traz_trades_deploy_alertas_e_corretoras(ctl):
    base, run, mp, tmp = ctl
    mp.setenv("QUANT_TRADES_LOG", str(tmp / "t.csv"))
    mp.setenv("QUANT_DEPLOY_STATUS", str(tmp / "deploy.json"))
    (tmp / "deploy.json").write_text(json.dumps({"state": "ok", "msg": "aplicado", "at": "x", "id": "1"}))
    st = json.loads(urllib.request.urlopen(base + "/api/status").read())
    assert st["trades"]["count"] == 0 and st["deploy"]["last"]["state"] == "ok"
    assert set(st["venues"]) == {"binance", "kalshi", "polymarket"} and st["venues"]["polymarket"]["modos"] == []
    assert "canais" in st["alerts"]
    assert urllib.request.urlopen(base + "/api/trades.csv").status == 200


def test_unidades_novas_nao_leem_o_env_das_chaves_e_o_polkit_so_libera_start():
    for name in ("quant-alert.service", "quant-deploy.service", "quant-rollback.service"):
        txt = (DEPLOY / name).read_text()
        body = "\n".join(ln for ln in txt.splitlines() if not ln.startswith("#"))
        assert "quant-live.env" not in body and "NoNewPrivileges=yes" in body and "User=quant" in body, name
    rule = (DEPLOY / "50-quant-control.rules").read_text()
    for u in ("quant-alert.service", "quant-deploy.service", "quant-rollback.service"):
        assert f'"{u}"' in rule
    assert 'unit === "quant-control.service" && verb === "restart"' in rule and "manage-unit-files" not in rule


# ---- atualizar.sh: so roda no Linux (usa bash/tar/venv) --------------------------------------------------------
@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="precisa de Linux com bash")
class TestAtualizar:
    def run_script(self, tmp_path, name="atualizar.sh"):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "QUANT_APP": str(tmp_path / "app"),
               "QUANT_DATA": str(tmp_path / "data"), "QUANT_PY": sys.executable, "QUANT_NO_RESTART": "1"}
        return subprocess.run(["bash", str(DEPLOY / name)], capture_output=True, text=True, env=env, timeout=600)

    def status(self, tmp_path):
        return json.loads((tmp_path / "data" / "deploy.json").read_text())

    def fake_project(self, tmp_path, *, passing=True):
        src = tmp_path / "pkg" / "src" / "quant"
        (src / "live").mkdir(parents=True)
        for mod in ("__init__", "control", "alerts", "selfcheck", "live/__init__", "live/config"):
            (src / f"{mod}.py").write_text("")
        body = "True" if passing else "False"
        (tmp_path / "pkg" / "test_x.py").write_text(f"def test_ok():\n    assert {body}\n")
        pkg = tmp_path / "data" / "inbox" / "quant.tar.gz"
        pkg.parent.mkdir(parents=True)
        subprocess.run(["tar", "-czf", str(pkg), "-C", str(tmp_path / "pkg"), "."], check=True)
        (tmp_path / "app").mkdir()

    def test_sem_pacote_falha_com_mensagem(self, tmp_path):
        (tmp_path / "app").mkdir()
        r = self.run_script(tmp_path)
        assert r.returncode != 0 and self.status(tmp_path)["state"] == "erro"

    def test_pacote_com_teste_falhando_nao_e_aplicado(self, tmp_path):
        self.fake_project(tmp_path, passing=False)
        r = self.run_script(tmp_path)
        assert r.returncode != 0 and self.status(tmp_path)["state"] == "erro"
        assert not (tmp_path / "app" / "src").exists()  # nada foi aplicado

    def test_pacote_bom_e_aplicado_com_backup_e_reverte(self, tmp_path):
        self.fake_project(tmp_path)
        (tmp_path / "app" / "antigo.txt").write_text("v1")
        r = self.run_script(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert self.status(tmp_path)["state"] == "ok" and (tmp_path / "app" / "src" / "quant" / "control.py").exists()
        assert list((tmp_path / "data" / "backups").glob("pre-*.tar.gz"))
        assert not (tmp_path / "data" / "inbox" / "quant.tar.gz").exists()  # consumido: nao reaplica sozinho
        r2 = self.run_script(tmp_path, "reverter.sh")
        assert r2.returncode == 0 and self.status(tmp_path)["state"] == "ok"

    def test_caminho_malicioso_e_recusado(self, tmp_path):
        (tmp_path / "x").mkdir()
        (tmp_path / "x" / "a").write_text("x")
        inbox = tmp_path / "data" / "inbox"
        inbox.mkdir(parents=True)
        subprocess.run(["tar", "-czf", str(inbox / "quant.tar.gz"), "-C", str(tmp_path / "x"), "--transform",
                        "s,^a,../escapou,", "a"], check=True)
        (tmp_path / "app").mkdir()
        r = self.run_script(tmp_path)
        assert r.returncode != 0 and "recusado" in self.status(tmp_path)["msg"]

    def test_reverter_sem_backup_avisa(self, tmp_path):
        (tmp_path / "app").mkdir()
        (tmp_path / "data").mkdir()
        r = self.run_script(tmp_path, "reverter.sh")
        assert r.returncode != 0 and "backup" in self.status(tmp_path)["msg"]
