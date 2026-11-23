import pandas as pd
import pytest

from quant.live.executor import PaperExecutor
from quant.live.feed import Feed
from quant.live.risk import RiskLimits, RiskManager
from quant.live.runner import Runner

T0 = pd.Timestamp("2026-03-02 10:00")
BAR = pd.Timedelta(minutes=5)


def make_df(rows):
    """rows: [(o, h, l, c), ...] a partir de T0, barras de 5 min."""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "datetime", [T0 + i * BAR for i in range(len(rows))])
    return df


class FakeFeed(Feed):
    def __init__(self, rows):
        self.rows = list(rows)

    def closed_bars(self, n):
        return make_df(self.rows)


def sig_fn(sigs, atr=10.0):
    """Sinal fixo por indice de barra; ATR constante."""
    def f(bars):
        out = bars.copy()
        out["signal"] = [sigs.get(i, 0) for i in range(len(out))]
        out["atr"] = atr
        return out
    return f


def make_runner(tmp_path, rows, sigs, *, now=None, max_loss=1000.0, qty=1.0, **kw):
    feed = FakeFeed(rows)
    risk = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=max_loss))
    ex = PaperExecutor(slippage=0.0, fee_rate=0.0)
    clock = [now or (T0 + 5 * BAR + pd.Timedelta(seconds=2))]
    r = Runner(feed, ex, risk, sig_fn(sigs), qty=qty, stop_atr=2.0, state_path=tmp_path / "s.json",
               kill_file=tmp_path / "KILL", now_fn=lambda: clock[0], **kw)
    return r, feed, ex, risk


FLAT = [(100, 101, 99, 100)] * 4


def test_paper_slippage_e_taxa_contra_voce():
    ex = PaperExecutor(slippage=0.01, fee_rate=0.001)
    buy = ex.market_order(1, 2.0, 100.0)
    assert buy.price == pytest.approx(101.0) and buy.fee == pytest.approx(0.202)
    sell = ex.close_position(110.0)
    assert sell.price == pytest.approx(108.9)  # venda recebe menos
    assert ex.position() is None


def test_paper_um_trade_por_vez():
    ex = PaperExecutor()
    ex.market_order(1, 1.0, 100.0)
    with pytest.raises(ValueError):
        ex.market_order(1, 1.0, 100.0)


def test_risco_bloqueia_qty_dado_atrasado_e_perda_diaria():
    r = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=10.0, max_data_age_s=60))
    now = pd.Timestamp("2026-03-02 12:00:10")
    assert r.check_entry(1.0, now, pd.Timestamp("2026-03-02 12:00:00"))[0]
    assert not r.check_entry(2.0, now, pd.Timestamp("2026-03-02 12:00:00"))[0]
    assert not r.check_entry(1.0, now, pd.Timestamp("2026-03-02 11:50:00"))[0]
    r.record_trade(-10.0, now)
    ok, why = r.check_entry(1.0, now, pd.Timestamp("2026-03-02 12:00:00"))
    assert not ok and "perda diaria" in why
    # novo dia zera os contadores de dia, mas o halt continua ate ser revisto por um humano
    assert r.halted


def test_runner_entra_no_sinal_e_ignora_barra_repetida(tmp_path):
    r, feed, ex, _ = make_runner(tmp_path, FLAT + [(100, 101, 99, 100)], {4: 1})
    assert r.step() == "entrada"
    pos = ex.position()
    assert pos.side == 1 and pos.entry == 100
    assert r.stop == pytest.approx(100 - 2.0 * 10.0)
    assert r.step() == "sem_barra_nova"  # mesma barra => nao reprocessa nem reenvia ordem


def test_runner_stop_por_software(tmp_path):
    rows = FLAT + [(100, 101, 99, 100)]
    r, feed, ex, risk = make_runner(tmp_path, rows, {4: 1})
    r.step()
    feed.rows.append((100, 100, 79, 85))  # minima 79 < stop 80
    r.signals = sig_fn({})
    assert r.step() == "stop"
    assert ex.position() is None
    assert risk.state()["pnl"] == pytest.approx(-20.0)  # saiu no preco do stop


def test_runner_nao_entra_com_feed_atrasado(tmp_path):
    late = T0 + 5 * BAR + pd.Timedelta(minutes=30)
    r, _, ex, _ = make_runner(tmp_path, FLAT + [(100, 101, 99, 100)], {4: 1}, now=late)
    assert r.step() == "bloqueada"
    assert ex.position() is None


def test_kill_switch_fecha_posicao_e_trava(tmp_path):
    r, feed, ex, risk = make_runner(tmp_path, FLAT + [(100, 101, 99, 100)], {4: 1})
    r.step()
    (tmp_path / "KILL").write_text("")
    assert r.step() == "kill"
    assert ex.position() is None and risk.halted


def test_estado_persiste_e_posicao_orfa_trava_entradas(tmp_path):
    r, feed, ex, _ = make_runner(tmp_path, FLAT + [(100, 101, 99, 100)], {4: 1})
    r.step()
    # reinicio com a mesma posicao e o estado em disco: stop restaurado
    risk2 = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1000.0))
    r2 = Runner(feed, ex, risk2, sig_fn({}), qty=1.0, state_path=tmp_path / "s.json", kill_file=tmp_path / "KILL")
    assert r2.stop == pytest.approx(80.0) and not risk2.halted
    # reinicio com posicao na corretora mas sem estado: trava
    (tmp_path / "s.json").unlink()
    risk3 = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1000.0))
    Runner(feed, ex, risk3, sig_fn({}), qty=1.0, state_path=tmp_path / "s.json", kill_file=tmp_path / "KILL")
    assert risk3.halted


def test_runner_sem_look_ahead_estrategia_real(tmp_path):
    """A estrategia real do backtest roda sobre as barras fechadas sem quebrar o contrato (signal/atr)."""
    from quant.strategies import trend_follow as tf

    n = 120
    rows = [(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(n)]
    out = tf.generate_signals(tf.add_indicators(make_df(rows)), session_start="00:00", session_end="23:59")
    assert {"signal", "atr"} <= set(out.columns)
