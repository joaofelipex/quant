"""Varios ativos: registro, MultiRunner, tamanho por valor, status por ativo, configuracao e ordem manual por ativo."""
import json
import logging
from pathlib import Path
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
        assert assets.parse("nvda,AAPL") == ["NVDA", "AAPL"]
        assert assets.parse("tudo") == list(assets.ALL) and len(assets.ALL) > 100

    @pytest.mark.parametrize("bad", ["XYZ", "BTC,FOO", "KXETHPERP1", "1", "BTC;ETH"])
    def test_parse_recusa_desconhecido(self, bad):
        with pytest.raises(ValueError):
            assets.parse(bad)

    def test_catalogo_cobre_acoes_cambio_metais_e_os_20_cripto(self):
        classes = {r["cls"] for r in assets.rows()}
        assert {"Equities", "Crypto", "FX", "Metals", "Indices"} <= classes
        assert {"NVDA", "AAPL", "AUDUSD"} <= set(assets.ALL) and set(assets.CRYPTO) <= set(assets.ALL)
        assert all(r["ticker"] == f"KX{r['id']}PERP1" for r in assets.rows())

    def test_feed_da_binance_so_para_os_20_cripto(self):
        assert assets.uses_binance("BTC") and not assets.uses_binance("NVDA") and not assets.uses_binance("C")
        assert assets.symbol("BTC") == "BTC/USDT:USDT" and assets.ticker("NVDA") == "KXNVDAPERP1"
        assert len(set(assets.CRYPTO)) == len(assets.CRYPTO) == 20


class FakeRunner:
    def __init__(self, result="ok", pnl=0.0, bar_s=60, boom=False, kill_file=None):
        self.result, self.bar_s, self.boom, self.calls = result, bar_s, boom, 0
        self.kill_file = kill_file or Path("/nao/existe/KILL")
        self.risk = RiskManager(RiskLimits(max_qty=1e9, max_daily_loss=1e9))
        self.risk._pnl = pnl

    def step(self):
        self.calls += 1
        if self.boom:
            raise OSError("rede")
        return self.result


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class TestMulti:
    def test_um_ativo_com_erro_nao_para_os_outros(self, caplog):
        a, b = FakeRunner(boom=True), FakeRunner("entrada")
        with caplog.at_level(logging.ERROR):
            res = MultiRunner({"A": a, "B": b}, clock=Clock()).step_due()
        assert res == {"A": "erro", "B": "entrada"} and b.calls == 1 and "A" in caplog.text

    def test_cada_ativo_so_roda_na_sua_hora(self):
        clock = Clock(1_000_020.0)
        a, b = FakeRunner(bar_s=60), FakeRunner(bar_s=300)
        m = MultiRunner({"A": a, "B": b}, clock=clock)
        assert set(m.step_due()) == {"A", "B"}
        assert m.due["A"] == pytest.approx(1_000_020.0 - 1_000_020.0 % 60 + 60 + 2)
        assert m.due["B"] == pytest.approx(1_000_020.0 - 1_000_020.0 % 300 + 300 + 2)
        assert m.step_due() == {}  # ninguem venceu ainda
        clock.t = m.due["A"]
        assert set(m.step_due()) == {"A"} and b.calls == 1

    def test_erro_repete_em_5s_so_para_o_ativo_com_erro(self):
        clock = Clock(1_000_000.0)
        a, b = FakeRunner(boom=True), FakeRunner()
        m = MultiRunner({"A": a, "B": b}, clock=clock)
        m.step_due()
        assert m.due["A"] == pytest.approx(1_000_005.0)
        assert m.due["B"] == pytest.approx(1_000_022.0)  # proxima barra de 60 s + 2 s
        clock.t = 1_000_006.0
        assert set(m.step_due()) == {"A"}

    def test_roda_em_paralelo(self):
        import threading
        import time as _t

        vistos = set()

        class Lento(FakeRunner):
            def step(self):
                vistos.add(threading.current_thread().name)
                _t.sleep(0.05)
                return "ok"

        m = MultiRunner({f"A{i}": Lento() for i in range(8)}, workers=8, clock=Clock())
        t0 = _t.time()
        assert len(m.step_due()) == 8
        assert _t.time() - t0 < 0.3 and len(vistos) > 1  # 8 x 50 ms em serie levaria 400 ms

    def test_perda_total_trava_entradas_de_todos(self):
        a, b = FakeRunner(pnl=-3.0), FakeRunner(pnl=-2.5)
        m = MultiRunner({"A": a, "B": b, "C": FakeRunner()}, max_total_loss=5.0, clock=Clock())
        assert m.total_pnl() == -5.5
        m.step_due()
        assert all(r.risk.halted for r in m.runners.values())
        assert "perda total" in a.risk.halt_reason

    def test_sem_limite_ou_abaixo_dele_nao_trava(self):
        m = MultiRunner({"A": FakeRunner(pnl=-1.0)}, max_total_loss=5.0, clock=Clock())
        m.step_due()
        assert not m.runners["A"].risk.halted
        m2 = MultiRunner({"A": FakeRunner(pnl=-999.0)}, clock=Clock())
        m2.step_due()
        assert not m2.runners["A"].risk.halted

    def test_kill_vence_a_agenda_e_encerra(self, tmp_path):
        kf = tmp_path / "KILL"
        kf.write_text("")
        clock = Clock()
        m = MultiRunner({"A": FakeRunner("kill", kill_file=kf), "B": FakeRunner("kill", kill_file=kf)},
                        sleep=clock.sleep, clock=clock)
        m.due = {"A": clock.t + 3600, "B": clock.t + 3600}  # longe no futuro: o kill nao espera
        m.run()
        assert m.last == {"A": "kill", "B": "kill"}

    def test_sem_ativos_e_erro(self):
        with pytest.raises(ValueError):
            MultiRunner({})


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
    def test_direcao_so_long_ou_ambos(self, tmp_path):
        p = tmp_path / "rt.env"
        assert control.write_runtime(p, {"QUANT_DIRECTION": "long"})["QUANT_DIRECTION"] == "long"
        with pytest.raises(control.SettingError):
            control.write_runtime(p, {"QUANT_DIRECTION": "short"})

    def test_quant_assets_normaliza_e_valida(self, tmp_path):
        p = tmp_path / "rt.env"
        saved = control.write_runtime(p, {"QUANT_ASSETS": "btc, eth", "QUANT_NOTIONAL": "30"})
        assert saved["QUANT_ASSETS"] == "BTC,ETH" and saved["QUANT_NOTIONAL"] == "30"
        assert control.write_runtime(p, {"QUANT_ASSETS": ""})["QUANT_ASSETS"] == ""  # volta ao modo de um ativo
        for bad in ({"QUANT_ASSETS": "FOO"}, {"QUANT_NOTIONAL": "0"}, {"QUANT_NOTIONAL": "5000"},
                    {"QUANT_MAX_TOTAL_LOSS": "-1"}):
            with pytest.raises(control.SettingError):
                control.write_runtime(p, bad)


class FakeKalshiEx(PaperExecutor):
    def __init__(self, contract_price=5.0, min_qty=1.0):
        super().__init__()
        self.contract_price, self.min_qty = contract_price, min_qty


class TestBuildMulti:
    ENV = {"QUANT_MODE": "testnet", "QUANT_VENUE": "kalshi", "QUANT_ASSETS": "BTC,NVDA", "QUANT_NOTIONAL": "40",
           "QUANT_TIMEFRAME": "1m", "QUANT_STATE": "/x/y/live_state.json", "QUANT_MAX_TOTAL_LOSS": "7",
           "QUANT_TRADES_LOG": "/x/trades.csv"}

    @pytest.fixture(autouse=True)
    def fakes(self, monkeypatch):
        self.tickers, self.kalshi_feeds, self.prices = [], [], {}

        def build(mode, env, ticker=None):
            self.tickers.append(ticker)
            return FakeKalshiEx(self.prices.get(ticker, 5.0))

        monkeypatch.setattr(config, "build_kalshi", build)
        monkeypatch.setattr(config, "build_feed", lambda *a, **k: FakeFeed())
        monkeypatch.setattr(config, "KalshiFeed", lambda tk, tf, env="demo": self.kalshi_feeds.append(tk) or FakeFeed())

    def test_monta_um_runner_por_ativo_e_escolhe_o_feed(self):
        m = config.build_multi(self.ENV.get)
        assert list(m.runners) == ["BTC", "NVDA"] and self.tickers == ["KXBTCPERP1", "KXNVDAPERP1"]
        assert self.kalshi_feeds == ["KXNVDAPERP1"]  # BTC usa a Binance; NVDA, as velas da Kalshi
        btc = m.runners["BTC"]
        assert btc.notional == 40.0 and btc.label == "kalshi/testnet:BTC" and m.max_total_loss == 7.0
        assert btc.state_path.name == "live_state.BTC.json" and str(btc.trades_path).endswith("trades.csv")

    def test_pula_ativo_cujo_menor_contrato_passa_do_valor_por_entrada(self, caplog):
        self.prices["KXNVDAPERP1"] = 90.0  # 1 contrato = 90 USD > 1,5 x 40
        with caplog.at_level(logging.WARNING):
            m = config.build_multi(self.ENV.get)
        assert list(m.runners) == ["BTC"] and "NVDA fora" in caplog.text

    def test_mercado_que_falha_nao_derruba_os_outros(self, monkeypatch, caplog):
        original = config.build_kalshi

        def build(mode, env, ticker=None):
            if ticker == "KXBTCPERP1":
                raise OSError("fora do ar")
            return original(mode, env, ticker)

        monkeypatch.setattr(config, "build_kalshi", build)
        with caplog.at_level(logging.ERROR):
            m = config.build_multi(self.ENV.get)
        assert list(m.runners) == ["NVDA"] and "nao consegui preparar BTC" in caplog.text

    def test_nenhum_ativo_possivel(self, monkeypatch):
        def build(*a, **k):
            raise OSError("x")

        monkeypatch.setattr(config, "build_kalshi", build)
        with pytest.raises(SystemExit, match="nenhum"):
            config.build_multi(self.ENV.get)

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


class TestKalshiFeed:
    """Velas da Kalshi -> barras no formato canonico, preco por unidade do ativo."""

    MARKET = {"market": {"contract_size": "0.020000", "underlying_multiplier": "1.000000"}}

    @staticmethod
    def candle(end_ts, o, h, low, c, with_price=True):
        base = {"end_period_ts": end_ts, "bid": {"open": str(o - 0.01), "high": str(h - 0.01), "low": str(low - 0.01),
                                                 "close": str(c - 0.01)},
                "ask": {"open": str(o + 0.01), "high": str(h + 0.01), "low": str(low + 0.01), "close": str(c + 0.01)}}
        if with_price:
            base["price"] = {"open": str(o), "high": str(h), "low": str(low), "close": str(c)}
        return base

    def feed(self, tf="1m", now=6_000_000, calls=None):
        from quant.live.feed import KalshiFeed

        def fetch(url):
            if "candlesticks" not in url:
                return self.MARKET
            q = dict(kv.split("=") for kv in url.split("?")[1].split("&"))
            if calls is not None:
                calls.append(q)
            per, start, end = int(q["period_interval"]) * 60, int(q["start_ts"]), int(q["end_ts"])
            out = []
            t = end - end % per
            while t > start:  # uma vela por periodo: close = indice, para conferir ordem e agregacao
                out.append(self.candle(t, 7.0, 7.1, 6.9, 7.0 + (t // per) % 10 / 100))
                t -= per
            return {"candlesticks": out[::-1]}

        return KalshiFeed("KXAAPLPERP1", tf, now=lambda: now, fetch=fetch)

    def test_precos_por_unidade_do_ativo_e_barras_fechadas(self):
        df = self.feed().closed_bars(5)
        assert list(df.columns) == ["datetime", "open", "high", "low", "close"] and len(df) == 5
        assert df["open"].iloc[0] == pytest.approx(7.0 / 0.02)  # 7.0 por contrato de 0.02 -> 350 por unidade
        assert df["datetime"].is_monotonic_increasing and df["datetime"].iloc[-1] < pd.Timestamp(6_000_000, unit="s")

    def test_agrega_1m_em_5m_so_com_baldes_completos(self):
        df = self.feed("5m").closed_bars(4)
        assert len(df) == 4 and all(t.minute % 5 == 0 for t in df["datetime"])
        assert df["high"].iloc[-1] == pytest.approx(7.1 / 0.02) and df["low"].iloc[-1] == pytest.approx(6.9 / 0.02)

    def test_incremental_busca_so_o_que_falta(self):
        calls: list = []
        f = self.feed(calls=calls, now=6_000_000)
        f.closed_bars(300)
        antes = len(calls)
        f.now = lambda: 6_000_060  # passou 1 minuto
        f.closed_bars(300)
        novas = calls[antes:]
        assert len(novas) == 1 and int(novas[0]["end_ts"]) - int(novas[0]["start_ts"]) <= 180

    def test_vela_sem_negocio_usa_o_meio_do_livro(self):
        from quant.live.feed import KalshiFeed

        f = KalshiFeed.__new__(KalshiFeed)
        assert f._ohlc(self.candle(60, 7.0, 7.1, 6.9, 7.05, with_price=False)) == pytest.approx((7.0, 7.1, 6.9, 7.05))
        assert f._ohlc({"end_period_ts": 60}) is None

    def test_timeframe_invalido(self):
        from quant.live.feed import KalshiFeed

        with pytest.raises(ValueError, match="nao suportado"):
            KalshiFeed("KXAAPLPERP1", "3m", fetch=lambda u: self.MARKET)


class TestSemMargem:
    """available_balance_too_low: pula a barra em vez de repetir a cada 5 s (e nao derruba os outros ativos)."""

    def test_kalshi_traduz_o_codigo_de_saldo(self):
        from quant.live.executor import InsufficientFunds
        from quant.live.kalshi import KalshiError, KalshiPerpsExecutor

        ex = KalshiPerpsExecutor.__new__(KalshiPerpsExecutor)
        ex.ticker = "KXDOGEPERP1"
        ex.unit, ex.tick, ex.whole, ex.min_qty, ex.market_version, ex.subaccount = 100.0, 0.0001, True, 1.0, 1, None
        ex.basis, ex.rebase = 1.0, False
        ex._market = lambda: {"status": "active", "bid": "5.5", "ask": "5.6", "price": "5.55"}
        ex.position = lambda: None

        def sem_saldo(*a, **k):
            raise KalshiError("POST /margin/orders -> HTTP 400", "available_balance_too_low")

        ex._req = sem_saldo
        with pytest.raises(InsufficientFunds, match="margem insuficiente"):
            ex.market_order(1, 500, 0.0551)
        with pytest.raises(KalshiError):  # fechar (reduce_only) nunca vira "sem margem": e outro problema
            ex.market_order(-1, 500, 0.0551, reduce_only=True)

    def test_runner_pula_a_barra_e_marca_como_processada(self, caplog):
        from quant.live.executor import InsufficientFunds

        class SemMargem(PaperExecutor):
            def market_order(self, *a, **k):
                raise InsufficientFunds("KXDOGEPERP1: saldo/margem insuficiente")

        bars = pd.DataFrame({"datetime": pd.date_range("2026-01-01", periods=5, freq="1min"),
                             "open": 1.0, "high": 1.0, "low": 1.0, "close": 50.0})

        class Feed:
            def closed_bars(self, n):
                return bars

        def sinais(b):
            return b.assign(signal=1, atr=1.0)

        r = Runner(Feed(), SemMargem(), RiskManager(RiskLimits(max_qty=1e9, max_daily_loss=1e9)), sinais, qty=0.0,
                   notional=25.0, timeframe="1m", state_path="/nao/grava.json")
        r._save = lambda: None
        r.now_fn = lambda: pd.Timestamp("2026-01-01 00:05:10")
        with caplog.at_level(logging.WARNING):
            assert r.step() == "sem_margem"
        assert "entrada pulada" in caplog.text and r.entry is None and r.stop is None
        assert r.last_bar == bars.iloc[-1]["datetime"]  # barra processada: nao repete a cada 5 s
        assert r.step() == "sem_barra_nova"


class TestDadosRuins:
    """Picos falsos da demo: vela com amplitude absurda some; livro longe do preco justo nao vira fill."""

    def test_feed_descarta_pico_falso_e_mantem_as_velas_boas(self):
        from quant.live.feed import KalshiFeed

        f = KalshiFeed.__new__(KalshiFeed)
        f.MAX_RANGE = KalshiFeed.MAX_RANGE
        f.MAX_JUMP = KalshiFeed.MAX_JUMP
        close = [100.0, 100.1, 100.2, 100.1, 160.0, 100.3, 100.2, 100.4]  # um pico de +60% no meio
        df = pd.DataFrame({"ts": range(len(close)), "open": close, "high": [c * 1.001 for c in close],
                           "low": [c * 0.999 for c in close], "close": close})
        limpo = f._drop_spikes(df)
        assert 160.0 not in set(limpo["close"]) and len(limpo) == len(close) - 1
        calmo = pd.DataFrame({"ts": range(7), "open": 100.0, "high": 100.1, "low": 99.9,
                              "close": [100.0, 100.1, 100.2, 100.1, 100.3, 100.2, 100.4]})
        calmo.loc[2, "high"] = 130.0  # amplitude de 30% numa vela de 1 min, com o fechamento normal
        assert len(f._drop_spikes(calmo)) == 6
        assert len(f._drop_spikes(df.iloc[:2])) == 2  # poucos dados: nao mexe

    def test_ordem_ignora_oferta_solta_longe_do_preco_justo(self):
        from quant.live.kalshi import KalshiPerpsExecutor

        ex = KalshiPerpsExecutor.__new__(KalshiPerpsExecutor)
        ex.ticker, ex.unit, ex.tick, ex.whole, ex.min_qty = "KXALUMINUMPERP1", 0.001, 0.0001, True, 1.0
        ex.market_version, ex.subaccount, ex.basis, ex.rebase = 1, None, 1.0, False
        # mercado em 2.76, mas um ask perdido em 20.0 (o caso real: short fechado a 20.000 por unidade)
        ex._market = lambda: {"status": "active", "bid": "2.75", "ask": "20.0", "price": "2.76"}
        enviadas = []

        def req(method, path, **k):
            if method == "POST":
                enviadas.append(k["body"])
                return {"fill_count": "0"}
            return {"positions": []}

        ex._req = req
        with pytest.raises(Exception, match="sem fill"):  # nao enche porque nao ha liquidez perto do preco justo
            ex.market_order(1, 0.004, 2762.0)
        assert float(enviadas[0]["price"]) < 2.76 * 1.02  # o limite foi montado em volta de 2.76, nunca de 20

    def test_livro_normal_continua_usando_o_livro(self):
        from quant.live.kalshi import KalshiPerpsExecutor

        ex = KalshiPerpsExecutor.__new__(KalshiPerpsExecutor)
        ex.ticker, ex.unit, ex.tick, ex.whole, ex.min_qty = "KXETHPERP1", 0.001, 0.0001, True, 1.0
        ex.market_version, ex.subaccount, ex.basis, ex.rebase = 1, None, 1.0, False
        ex._market = lambda: {"status": "active", "bid": "1.67", "ask": "1.68", "price": "1.675"}
        enviadas = []
        ex._req = lambda m, p, **k: enviadas.append(k.get("body")) or {"fill_count": "0"}
        with pytest.raises(Exception, match="sem fill"):
            ex.market_order(1, 0.002, 1675.0)
        assert float(enviadas[0]["price"]) == pytest.approx(1.68 * 1.01, abs=0.0002)


class TestSoLong:
    """QUANT_DIRECTION=long: nunca abre short, mas o sinal de venda ainda fecha uma compra aberta."""

    def runner(self, sinal, long_only, pos=None):
        bars = pd.DataFrame({"datetime": pd.date_range("2026-01-01", periods=5, freq="1min"),
                             "open": 50.0, "high": 51.0, "low": 49.0, "close": 50.0})

        class Feed:
            def closed_bars(self, n):
                return bars

        ex = PaperExecutor()
        r = Runner(Feed(), ex, RiskManager(RiskLimits(max_qty=1e9, max_daily_loss=1e9)),
                   lambda b: b.assign(signal=sinal, atr=1.0), qty=1.0, timeframe="1m", state_path="/nao/grava.json",
                   long_only=long_only)
        r._save = lambda: None
        r.now_fn = lambda: pd.Timestamp("2026-01-01 00:05:10")
        if pos is not None:
            ex.market_order(pos, 1.0, 50.0)
            r.entry, r.stop, r.stop_dist = {"side": pos, "qty": 1.0, "price": 50.0}, 50.0 - pos * 2.0, 2.0
        return r, ex

    def test_com_long_only_o_sinal_de_venda_nao_abre_short(self):
        r, ex = self.runner(-1, True)
        assert r.step() == "ok" and ex.position() is None

    def test_sem_long_only_o_short_abre(self):
        r, ex = self.runner(-1, False)
        assert r.step() == "entrada" and ex.position().side == -1

    def test_long_only_ainda_abre_long(self):
        r, ex = self.runner(1, True)
        assert r.step() == "entrada" and ex.position().side == 1

    def test_sinal_de_venda_fecha_a_compra_aberta_mas_nao_vira_short(self):
        r, ex = self.runner(-1, True, pos=1)
        assert r.step() == "saida_sinal" and ex.position() is None

    def test_configuracao_pelo_ambiente(self, monkeypatch):
        monkeypatch.setattr(config, "build_kalshi", lambda mode, env, ticker=None: FakeKalshiEx())
        monkeypatch.setattr(config, "build_feed", lambda *a, **k: FakeFeed())
        monkeypatch.setattr(config, "KalshiFeed", lambda *a, **k: FakeFeed())
        env = {**TestBuildMulti.ENV, "QUANT_DIRECTION": "long"}
        assert all(r.long_only for r in config.build_multi(env.get).runners.values())
        assert not any(r.long_only for r in config.build_multi(TestBuildMulti.ENV.get).runners.values())
