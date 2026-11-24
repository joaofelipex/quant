"""Boleta manual (quant.manual) e o endpoint do painel: validacao, travas e fluxo abrir/proteger/fechar."""
import json
import subprocess
from pathlib import Path

import pytest

from quant import control, manual
from quant.live.executor import Fill, Position
from quant.live.kalshi import KalshiError, StopRejected


class FakeEx:
    """Corretora falsa: guarda posicao, stop e registra o que foi chamado."""

    def __init__(self, pos=None, reject_stop=False, fail_order=False):
        self.pos, self.stop_called, self.cancelled = pos, None, 0
        self.reject_stop, self.fail_order = reject_stop, fail_order
        self.basis = 1.0

    def position(self):
        return self.pos

    def market_order(self, side, qty, hint, reduce_only=False):
        if self.fail_order:
            raise KalshiError("ordem IOC sem fill")
        self.pos = Position(side, qty, hint)
        return Fill(side, qty, hint, 0.0)

    def close_position(self, price):
        pos, self.pos = self.pos, None
        return Fill(-pos.side, pos.qty, price, 0.01) if pos else None

    def place_stop(self, side, qty, price):
        if self.reject_stop:
            raise StopRejected("stop recusado pela Kalshi: preco no lado errado")
        self.stop_called = (side, qty, price)

    def cancel_stops(self):
        self.cancelled += 1

    def has_stop(self):
        return self.stop_called is not None

    def export_state(self):
        return {"basis": self.basis}


def run(req, ex, tmp_path, price=2000.0, kill=False):
    kf = tmp_path / "KILL"
    if kill:
        kf.write_text("")
    return manual.execute(manual.validate(req), ex, price_fn=lambda: price, kill_file=kf,
                          trades_path=tmp_path / "trades.csv", save_basis=lambda s: None)


class TestValidate:
    @pytest.mark.parametrize("bad", [None, [], {"action": "rm"}, {"action": "open", "side": 2, "qty": 0.01},
                                     {"action": "open", "side": 1, "qty": 0}, {"action": "open", "side": 1, "qty": 1},
                                     {"action": "open", "side": 1, "qty": "x"},
                                     {"action": "open", "side": True, "qty": 0.01},
                                     {"action": "open", "side": 1, "qty": 0.01, "stop_pct": 50},
                                     {"action": "open", "side": 1, "qty": float("nan")},
                                     {"action": "stop"}])
    def test_recusa(self, bad):
        with pytest.raises(manual.OrderError):
            manual.validate(bad)

    def test_aceita(self):
        assert manual.validate({"action": "open", "side": -1, "qty": 0.02, "stop_pct": 1.5, "id": "a"}) == {
            "id": "a", "action": "open", "side": -1, "qty": 0.02, "stop_pct": 1.5}
        assert manual.validate({"action": "close"}) == {"id": "", "action": "close"}


class TestExecute:
    def test_abre_long_com_stop_abaixo(self, tmp_path):
        ex = FakeEx()
        r = run({"action": "open", "side": 1, "qty": 0.01, "stop_pct": 1}, ex, tmp_path)
        assert r["ok"] and "COMPRA" in r["msg"] and "aviso" not in r
        side, qty, price = ex.stop_called
        assert side == -1 and qty == 0.01 and price == pytest.approx(1980.0)  # 1% abaixo da entrada
        assert r["position"]["side"] == 1 and r["position"]["stop"] is True

    def test_abre_short_com_stop_acima(self, tmp_path):
        ex = FakeEx()
        run({"action": "open", "side": -1, "qty": 0.01, "stop_pct": 2}, ex, tmp_path)
        assert ex.stop_called[0] == 1 and ex.stop_called[2] == pytest.approx(2040.0)

    def test_stop_recusado_avisa_que_ficou_sem_stop(self, tmp_path):
        r = run({"action": "open", "side": 1, "qty": 0.01, "stop_pct": 1}, FakeEx(reject_stop=True), tmp_path)
        assert r["ok"] and "SEM stop" in r["aviso"]

    def test_sem_stop_informado_avisa(self, tmp_path):
        r = run({"action": "open", "side": 1, "qty": 0.01}, FakeEx(), tmp_path)
        assert r["ok"] and "SEM stop" in r["aviso"]

    def test_nao_abre_com_posicao_existente(self, tmp_path):
        ex = FakeEx(Position(1, 0.01, 2000.0))
        r = run({"action": "open", "side": -1, "qty": 0.01}, ex, tmp_path)
        assert not r["ok"] and "ja existe posicao" in r["msg"]

    def test_kill_bloqueia_abertura(self, tmp_path):
        r = run({"action": "open", "side": 1, "qty": 0.01}, FakeEx(), tmp_path, kill=True)
        assert not r["ok"] and "kill" in r["msg"].lower()

    def test_ordem_recusada_pela_corretora(self, tmp_path):
        r = run({"action": "open", "side": 1, "qty": 0.01}, FakeEx(fail_order=True), tmp_path)
        assert not r["ok"] and "recusada" in r["msg"]

    def test_sem_preco_nao_abre(self, tmp_path):
        ex = FakeEx()
        r = manual.execute(manual.validate({"action": "open", "side": 1, "qty": 0.01}), ex,
                           price_fn=lambda: (_ for _ in ()).throw(OSError("rede")), trades_path=None)
        assert not r["ok"] and ex.pos is None

    def test_fecha_grava_trade_manual_e_cancela_stop(self, tmp_path):
        ex = FakeEx(Position(1, 0.01, 2000.0))
        r = run({"action": "close"}, ex, tmp_path, price=2100.0)
        assert r["ok"] and r["position"] is None and ex.cancelled == 1
        rows = (tmp_path / "trades.csv").read_text().splitlines()
        assert rows[0].split(",") == manual.TRADE_FIELDS
        cols = rows[1].split(",")
        assert cols[1] == "kalshi/testnet" and cols[2] == "1" and cols[-1] == "manual"
        assert float(cols[6]) == pytest.approx(0.01 * 100 - 0.01)  # (2100-2000)*0.01 - taxa

    def test_fechar_sem_posicao_e_inofensivo(self, tmp_path):
        assert run({"action": "close"}, FakeEx(), tmp_path)["ok"]

    def test_stop_numa_posicao_existente(self, tmp_path):
        ex = FakeEx(Position(-1, 0.02, 2000.0))
        r = run({"action": "stop", "stop_pct": 1}, ex, tmp_path)
        assert r["ok"] and ex.stop_called == (1, 0.02, pytest.approx(2020.0))

    def test_stop_sem_posicao(self, tmp_path):
        assert not run({"action": "stop", "stop_pct": 1}, FakeEx(), tmp_path)["ok"]

    def test_status_mostra_pnl_aberto(self, tmp_path):
        r = run({"action": "status"}, FakeEx(Position(-1, 0.01, 2000.0)), tmp_path, price=1990.0)
        assert r["position"]["upnl"] == pytest.approx(0.1)


class TestMain:
    def env(self, tmp_path, **kw):
        base = {"QUANT_MODE": "testnet", "QUANT_VENUE": "kalshi", "QUANT_ORDER_REQUEST": str(tmp_path / "req.json"),
                "QUANT_ORDER_RESULT": str(tmp_path / "res.json"), "QUANT_STATE": str(tmp_path / "st.json"),
                "QUANT_KILL_FILE": str(tmp_path / "KILL")}
        base.update(kw)
        return base.get

    @pytest.mark.parametrize("env", [{"QUANT_MODE": "live"}, {"QUANT_MODE": "paper"}, {"QUANT_VENUE": "binance"}])
    def test_so_kalshi_demo(self, tmp_path, env):
        (tmp_path / "req.json").write_text(json.dumps({"id": "7", "action": "open", "side": 1, "qty": 0.01}))
        assert manual.main(self.env(tmp_path, **env)) == 1
        out = json.loads((tmp_path / "res.json").read_text())
        assert out["id"] == "7" and not out["ok"] and "so funciona" in out["msg"]

    def test_pedido_invalido_vira_resultado(self, tmp_path):
        (tmp_path / "req.json").write_text(json.dumps({"id": "8", "action": "open", "side": 1, "qty": 9}))
        assert manual.main(self.env(tmp_path)) == 1
        assert json.loads((tmp_path / "res.json").read_text())["id"] == "8"

    def test_arquivo_ausente_nao_derruba(self, tmp_path):
        assert manual.main(self.env(tmp_path)) == 1
        assert not json.loads((tmp_path / "res.json").read_text())["ok"]


class FakeRun:
    def __init__(self, runner="inactive", order="inactive", start_rc=0):
        self.state, self.calls, self.start_rc = {"quant-live": runner, "quant-order.service": order}, [], start_rc

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[1] == "is-active":
            name = cmd[2]
            return subprocess.CompletedProcess(cmd, 0, self.state.get(name, "inactive") + "\n", "")
        return subprocess.CompletedProcess(cmd, self.start_rc, "", "falhou" if self.start_rc else "")


class TestSubmit:
    def paths(self, tmp_path):
        return tmp_path / "req.json", tmp_path / "res.json"

    def test_grava_pedido_e_dispara(self, tmp_path):
        rq, rs = self.paths(tmp_path)
        rs.write_text("{}")
        fr = FakeRun()
        code, res = control.submit_order({"action": "open", "side": 1, "qty": 0.01, "stop_pct": 1}, rq, rs, fr)
        assert code == 202 and res["ok"] and json.loads(rq.read_text())["id"] == res["id"]
        assert not rs.exists() and ["systemctl", "start", "--no-block", "quant-order.service"] in fr.calls

    def test_abrir_exige_runner_parado_mas_fechar_nao(self, tmp_path):
        rq, rs = self.paths(tmp_path)
        code, res = control.submit_order({"action": "open", "side": 1, "qty": 0.01}, rq, rs, FakeRun(runner="active"))
        assert code == 409 and "pare o runner" in res["erro"] and not rq.exists()
        assert control.submit_order({"action": "close"}, rq, rs, FakeRun(runner="active"))[0] == 202
        assert control.submit_order({"action": "status"}, rq, rs, FakeRun(runner="active"))[0] == 202

    def test_ordem_em_andamento(self, tmp_path):
        code, res = control.submit_order({"action": "close"}, *self.paths(tmp_path), FakeRun(order="activating"))
        assert code == 409 and "em andamento" in res["erro"]

    def test_pedido_invalido_nem_chega_ao_systemd(self, tmp_path):
        fr = FakeRun()
        code, _ = control.submit_order({"action": "open", "side": 1, "qty": 5}, *self.paths(tmp_path), fr)
        assert code == 400 and fr.calls == []

    def test_falha_ao_disparar(self, tmp_path):
        code, res = control.submit_order({"action": "close"}, *self.paths(tmp_path), FakeRun(start_rc=1))
        assert code == 409 and res["erro"] == "falhou"

    def test_read_order(self, tmp_path):
        p = tmp_path / "res.json"
        assert control.read_order(p) == {"pendente": True}
        p.write_text(json.dumps({"id": "1", "ok": True}))
        assert control.read_order(p)["id"] == "1"


def test_unit_e_polkit_da_boleta():
    root = Path(__file__).resolve().parents[1] / "deploy"
    unit = (root / "quant-order.service").read_text()
    assert "quant.manual" in unit and "EnvironmentFile=/etc/quant-live.env" in unit
    assert "quant-order.service" in (root / "50-quant-control.rules").read_text()
    # o painel web NAO pode ter a chave: a unit do painel nao le o env das corretoras
    assert "EnvironmentFile=/etc/quant-live.env" not in (root / "quant-control.service").read_text()
