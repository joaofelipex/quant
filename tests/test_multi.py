"""Varios ativos: registro, MultiRunner, tamanho por valor, status por ativo, configuracao e ordem manual por ativo."""
import json
import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from quant import control, manual
from quant.live import assets, config
from quant.live.executor import Fill, PaperExecutor
from quant.live.multi import MultiRunner
from quant.live.risk import RiskLimits, RiskManager
from quant.live.runner import Runner


class TestAssets:
    def test_parse(self):
        assert assets.parse("btc, eth,BTC") == ["BTC", "ETH"]
        assert assets.parse("") == [] and assets.parse("todos") == list(assets.CRYPTO)

    @pytest.mark.parametrize("bad", ["XYZ", "BTC,FOO", "KXETHPERP1", "C", "CVX"])
    def test_parse_recusa_desconhecido_e_acoes(self, bad):
        with pytest.raises(ValueError):
            assets.parse(bad)

    def test_nomes(self):
        assert assets.symbol("BTC") == "BTC/USDT:USDT" and assets.ticker("SOL") == "KXSOLPERP1"
        assert len(set(assets.CRYPTO)) == len(assets.CRYPTO) == 20


class FakeRunner:
    def __init__(self, result="ok", pnl=0.0, bar_s=60, boom=False):
        self.result, self.bar_s, self.boom, self.pnl, self.calls = result, bar_s, boom, pnl, 0
        self.risk = RiskManager(RiskLimits(max_qty=1e9, max_daily_loss=1e9))

    def step(self):
        self.calls += 1
        if self.boom:
            raise OSError("rede")
        return self.result

    @property
    def risk_state(self):
        return self.risk.state()


def with_pnl(r, pnl):
    r.risk._pnl = pnl
    return r


class TestMulti:
    def test_um_ativo_com_erro_nao_para_os_outros(self, caplog):
        a, b = FakeRunner(boom=True), FakeRunner("entrada")
        with caplog.at_level(logging.ERROR):
            res = MultiRunner({"A": a, "B": b}).step_all()
        assert res == {"A": "erro", "B": "entrada"} and b.calls == 1 and "A" in caplog.text

    def test_perda_total_trava_entradas_de_todos(self):
        a, b = with_pnl(FakeRunner(), -3.0), with_pnl(FakeRunner(), -2.5)
        m = MultiRunner({"A": a, "B": b, "C": FakeRunner()}, max_total_loss=5.0)
        assert m.total_pnl() == -5.5
        m.step_all()
        assert all(r.risk.halted for r in m.runners.values())
        assert "TOTAL" not in a.risk.halt_reason and "perda total" in a.risk.halt_reason

    def test_sem_limite_ou_abaixo_dele_nao_trava(self):
        m = MultiRunner({"A": with_pnl(FakeRunner(), -1.0)}, max_total_loss=5.0)
        m.step_all()
        assert not m.runners["A"].risk.halted
        m2 = MultiRunner({"A": with_pnl(FakeRunner(), -999.0)})
        m2.step_all()
        assert not m2.runners["A"].risk.halted

    def test_run_encerra_quando_todos_dizem_kill(self):
        m = MultiRunner({"A": FakeRunner("kill"), "B": FakeRunner("kill")},
                        sleep=lambda s: pytest.fail("nao deve dormir"))
        m.run()

    def test_run_repete_logo_apos_erro_e_espera_a_barra_depois(self):
        a = FakeRunner()
        pausas, passos = [], iter(["erro", "ok", "kill"])
        a.step = lambda: (r := next(passos)) == "erro" and (_ for _ in ()).throw(OSError("x")) or r
        m = MultiRunner({"A": a}, sleep=pausas.append, clock=lambda: 120.0)
        m.run()
        assert pausas[0] == 5.0 and pausas[1] == pytest.approx(62.0)  # erro: 5 s; ok: 2 s depois do fechamento

    def test_sem_ativos_e_erro(self):
        with pytest.raises(ValueError):
            MultiRunner({})

    def test_usa_a_menor_barra(self):
        assert MultiRunner({"A": FakeRunner(bar_s=300), "B": FakeRunner(bar_s=60)}).bar_s == 60


class FakeFeed:
    def closed_bars(self, n):
        return pd.DataFrame({"datetime": [pd.Timestamp("2026-01-01")], "open": [1.0], "high": [1.0],
                             "low": [1.0], "close": [50.0]})


class TestTamanho:
    def make(self, **kw):
        return Runner(FakeFeed(), PaperExecutor(), RiskManager(RiskLimits(max_qty=1e9, max_daily_loss=1e9)),
                      lambda b: b, qty=0.01, **kw)

    def test_qty_fixa_sem_notional(self):
        assert self.make()._size(50_000) == 0.01

    def test_notional_da_o_mesmo_valor_em_qualquer_preco(self):
        r = self.make(notional=25.0)
        assert r._size(50_000) * 50_000 == pytest.approx(25.0) and r._size(0.05) * 0.05 == pytest.approx(25.0)


class TestStatusPorAtivo:
    def state(self, tmp_path, asset, pnl=0.0, entry=None):
        (tmp_path / f"live_state.{asset}.json").write_text(json.dumps({
            "last_bar": "2026-11-24 12:00:00", "stop": 99.0, "entry": entry,
            "risk": {"pnl": pnl, "trades": 2, "halted": pnl < -1, "reason": "perda" if pnl < -1 else ""}}))

    def test_resumo(self, tmp_path):
        self.state(tmp_path, "BTC", 0.5, {"side": 1, "qty": 0.001, "price": 60000.0})
        self.state(tmp_path, "SOL", -2.0)
        rows = control.assets_summary(tmp_path, ["BTC", "SOL", "ETH"], 1_795_000_000)
        assert [r["asset"] for r in rows] == ["BTC", "SOL", "ETH"]
        assert rows[0]["position"]["side"] == 1 and rows[0]["pnl"] == 0.5 and rows[0]["started"]
        assert rows[1]["halted"] and rows[1]["reason"] == "perda"
        assert not rows[2]["started"] and rows[2]["last_bar_age_s"] is None  # ainda sem arquivo de estado

    def test_status_escolhe_o_ativo(self, tmp_path, monkeypatch):
        self.state(tmp_path, "BTC", 0.5)
        self.state(tmp_path, "SOL", -2.0)
        vistos = []
        monkeypatch.setattr(control, "runner_config", lambda *a: {"QUANT_ASSETS": "BTC,SOL", "QUANT_TIMEFRAME": "1m"})
        monkeypatch.setattr(control, "recent_closes", lambda sym, tf, *a, **k: vistos.append(sym) or [[1, 2.0]])
        monkeypatch.setattr(control, "_run", lambda *a, **k: "active")
        s = control.build_status(tmp_path / "live_state.json", tmp_path / "KILL", asset="SOL")
        assert s["asset"] == "SOL" and s["state"]["risk"]["pnl"] == -2.0 and vistos == ["SOL/USDT:USDT"]
        assert len(s["assets"]) == 2
        padrao = control.build_status(tmp_path / "live_state.json", tmp_path / "KILL", asset="XXX")
        assert padrao["asset"] == "BTC"  # ativo invalido cai no primeiro

    def test_modo_de_um_ativo_continua_igual(self, tmp_path, monkeypatch):
        (tmp_path / "live_state.json").write_text(json.dumps({"last_bar": None, "risk": {}}))
        monkeypatch.setattr(control, "runner_config", lambda *a: {"QUANT_SYMBOL": "ETH/USDT:USDT"})
        monkeypatch.setattr(control, "recent_closes", lambda *a, **k: [])
        monkeypatch.setattr(control, "_run", lambda *a, **k: "active")
        s = control.build_status(tmp_path / "live_state.json", tmp_path / "KILL")
        assert s["asset"] is None and s["assets"] == []


class TestConfiguracoes:
    def test_quant_assets_normaliza_e_valida(self, tmp_path):
        p = tmp_path / "rt.env"
        saved = control.write_runtime(p, {"QUANT_ASSETS": "btc, eth", "QUANT_NOTIONAL": "30"})
        assert saved["QUANT_ASSETS"] == "BTC,ETH" and saved["QUANT_NOTIONAL"] == "30"
        assert control.write_runtime(p, {"QUANT_ASSETS": ""})["QUANT_ASSETS"] == ""  # volta ao modo de um ativo
        for bad in ({"QUANT_ASSETS": "FOO"}, {"QUANT_NOTIONAL": "0"}, {"QUANT_NOTIONAL": "5000"},
                    {"QUANT_MAX_TOTAL_LOSS": "-1"}):
            with pytest.raises(control.SettingError):
                control.write_runtime(p, bad)


class TestBuildMulti:
    ENV = {"QUANT_MODE": "testnet", "QUANT_VENUE": "kalshi", "QUANT_ASSETS": "BTC,ETH", "QUANT_NOTIONAL": "40",
           "QUANT_TIMEFRAME": "1m", "QUANT_STATE": "/x/y/live_state.json", "QUANT_MAX_TOTAL_LOSS": "7",
           "QUANT_TRADES_LOG": "/x/trades.csv"}

    @pytest.fixture(autouse=True)
    def fakes(self, monkeypatch):
        self.tickers = []
        monkeypatch.setattr(config, "build_kalshi",
                            lambda mode, env, ticker=None: self.tickers.append(ticker) or PaperExecutor())
        monkeypatch.setattr(config, "build_feed", lambda *a, **k: FakeFeed())

    def test_monta_um_runner_por_ativo(self):
        m = config.build_multi(self.ENV.get)
        assert list(m.runners) == ["BTC", "ETH"] and self.tickers == ["KXBTCPERP1", "KXETHPERP1"]
        btc = m.runners["BTC"]
        assert btc.notional == 40.0 and btc.label == "kalshi/testnet:BTC" and m.max_total_loss == 7.0
        assert btc.state_path.name == "live_state.BTC.json" and str(btc.trades_path).endswith("trades.csv")

    @pytest.mark.parametrize("over", [{"QUANT_VENUE": "binance"}, {"QUANT_MODE": "live"}, {"QUANT_MODE": "paper"}])
    def test_so_kalshi_demo(self, over):
        with pytest.raises(SystemExit, match="so funciona"):
            config.build_multi({**self.ENV, **over}.get)

    def test_ativo_invalido(self):
        with pytest.raises(SystemExit, match="desconhecido"):
            config.build_multi({**self.ENV, "QUANT_ASSETS": "FOO"}.get)


class TestOrdemManualPorAtivo:
    def test_validate_exige_usd_com_ativo(self):
        ok = manual.validate({"action": "open", "side": 1, "asset": "BTC", "usd": 30, "stop_pct": 1})
        assert ok["asset"] == "BTC" and ok["usd"] == 30.0 and "qty" not in ok
        for bad in ({"action": "open", "side": 1, "asset": "BTC", "qty": 0.01},
                    {"action": "open", "side": 1, "asset": "BTC", "usd": 999},
                    {"action": "open", "side": 1, "asset": "FOO", "usd": 10}):
            with pytest.raises(manual.OrderError):
                manual.validate(bad)

    def test_sem_ativo_continua_com_qty(self):
        assert manual.validate({"action": "open", "side": -1, "qty": 0.02})["qty"] == 0.02

    def test_abre_pelo_valor_em_dolares(self, tmp_path):
        class Ex:
            pos = None

            def position(self):
                return self.pos

            def market_order(self, side, qty, hint, reduce_only=False):
                self.qty = qty
                self.pos = SimpleNamespace(side=side, qty=qty, entry=hint)
                return Fill(side, qty, hint, 0.0)

            def place_stop(self, *a):
                pass

            def cancel_stops(self):
                pass

            def has_stop(self):
                return True

            def export_state(self):
                return {}

        ex = Ex()
        r = manual.execute(manual.validate({"action": "open", "side": 1, "asset": "BTC", "usd": 30, "stop_pct": 1}), ex,
                           price_fn=lambda: 60_000.0, trades_path=None)
        assert r["ok"] and ex.qty == pytest.approx(30 / 60_000)
