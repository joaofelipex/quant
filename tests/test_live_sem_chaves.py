"""Runner sem chaves: feed publico de spot, escolha do feed por modo e posicao do paper que sobrevive ao reinicio."""
import pandas as pd
import pytest
from test_live import BAR, FLAT, T0, PaperExecutor, sig_fn
from test_live_robustez import WindowFeed

from quant.live import config
from quant.live import feed as feed_mod
from quant.live.executor import BinanceFuturesExecutor
from quant.live.feed import CcxtFeed, PublicSpotFeed
from quant.live.risk import RiskLimits, RiskManager
from quant.live.runner import Runner

T0_MS = int(pd.Timestamp("2026-03-01", tz="UTC").timestamp() * 1000)


def klines(n):
    return [[T0_MS + i * 60_000, str(100 + i), str(101 + i), str(99 + i), str(100.5 + i), "1.0"] for i in range(n)]


# ---- feed publico -----------------------------------------------------------------------------------------------
def test_feed_publico_le_spot_descarta_a_barra_aberta_e_mapeia_o_simbolo(monkeypatch):
    urls = []

    def fake(url, **_):
        urls.append(url)
        return klines(5)

    monkeypatch.setattr(feed_mod, "get_json", fake)
    bars = PublicSpotFeed("ETH/USDT:USDT", "1m").closed_bars(4)
    assert urls == ["https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=1m&limit=5"]
    assert len(bars) == 4  # pediu n+1 e jogou fora a ultima (ainda em formacao)
    assert list(bars.columns) == ["datetime", "open", "high", "low", "close"]
    assert bars.close.iloc[-1] == 103.5 and bars.datetime.is_monotonic_increasing


def test_feed_publico_serve_ao_runner_com_a_estrategia_real(monkeypatch):
    from quant.strategies import trend_follow as tf

    monkeypatch.setattr(feed_mod, "get_json", lambda url, **_: klines(301))
    bars = PublicSpotFeed("ETH/USDT:USDT", "1m").closed_bars(300)
    out = tf.generate_signals(tf.add_indicators(bars), session_start="00:00", session_end="23:59")
    assert {"signal", "atr"} <= set(out.columns) and len(out) == 300


# ---- escolha do feed por modo -------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode,choice,esperado", [
    ("paper", "auto", PublicSpotFeed),   # o paper nao depende da API bloqueada por regiao
    ("testnet", "auto", CcxtFeed),
    ("live", "auto", CcxtFeed),
    ("paper", "ccxt", CcxtFeed),
    ("testnet", "public", PublicSpotFeed),
])
def test_build_feed_escolhe_pelo_modo(mode, choice, esperado):
    assert isinstance(config.build_feed(mode, "ETH/USDT:USDT", "1m", "testnet", choice), esperado)


def test_build_feed_recusa_opcao_invalida():
    with pytest.raises(SystemExit):
        config.build_feed("paper", "ETH/USDT:USDT", "1m", "testnet", "xyz")


def test_modo_paper_nao_exige_chave_nem_toca_o_executor_da_corretora(monkeypatch, tmp_path):
    for var in ("BINANCE_API_KEY", "BINANCE_API_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("QUANT_MODE", "paper")
    monkeypatch.setenv("QUANT_STATE", str(tmp_path / "s.json"))
    monkeypatch.setenv("QUANT_KILL_FILE", str(tmp_path / "KILL"))
    r = config.build_runner()
    assert isinstance(r.feed, PublicSpotFeed) and isinstance(r.executor, PaperExecutor)
    assert not isinstance(r.executor, BinanceFuturesExecutor)


# ---- persistencia do paper ------------------------------------------------------------------------------------------
def test_executor_paper_exporta_e_importa_a_posicao():
    a = PaperExecutor(slippage=0.0, fee_rate=0.0)
    assert a.export_state() == {"pos": None}
    a.market_order(-1, 2.0, 100.0)
    b = PaperExecutor(slippage=0.0, fee_rate=0.0)
    b.import_state(a.export_state())
    assert b.position() == a.position() and b.position().side == -1
    b.import_state({"pos": None})
    assert b.position() is None


def test_posicao_do_paper_sobrevive_ao_reinicio_do_processo(tmp_path):
    """Antes, reiniciar o servico apagava a posicao simulada em silencio (nem trade registrado, nem stop)."""
    rows = FLAT + [(100, 101, 99, 100)]
    feed = WindowFeed(rows)
    risk = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1000.0))
    r1 = Runner(feed, PaperExecutor(slippage=0.0, fee_rate=0.0), risk, sig_fn({4: 1}), qty=1.0, stop_atr=2.0,
                state_path=tmp_path / "s.json", kill_file=tmp_path / "KILL",
                now_fn=lambda: T0 + 5 * BAR + pd.Timedelta(seconds=2))
    assert r1.step() == "entrada"

    # processo novo: executor NOVO (memoria vazia), mesmo arquivo de estado
    ex2 = PaperExecutor(slippage=0.0, fee_rate=0.0)
    r2 = Runner(feed, ex2, RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1000.0)), sig_fn({}), qty=1.0,
                state_path=tmp_path / "s.json", kill_file=tmp_path / "KILL")
    assert ex2.position() is not None and ex2.position().entry == 100
    assert r2.stop == pytest.approx(80.0) and r2.entry["price"] == 100 and not r2.risk.halted
    feed.rows.append((100, 100, 79, 85))  # o stop continua funcionando depois do reinicio
    assert r2.step() == "stop" and ex2.position() is None


def test_estado_sem_chave_executor_de_corretora_nao_grava_nada_extra(tmp_path):
    class Real(PaperExecutor):
        def export_state(self):
            return None

    risk = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1.0))
    r = Runner(WindowFeed(FLAT), Real(slippage=0.0, fee_rate=0.0), risk, sig_fn({}), qty=1.0,
               state_path=tmp_path / "s.json", kill_file=tmp_path / "KILL", now_fn=lambda: T0 + 4 * BAR)
    r.step()
    assert '"executor": null' in (tmp_path / "s.json").read_text()

