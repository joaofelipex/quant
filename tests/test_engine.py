import numpy as np
import pytest
from conftest import TOY, make_bars

from quant.backtest.engine import run_backtest
from quant.instruments import WIN

D = "2026-03-02"


def bars(*rows, **kw):
    return make_bars([(f"{D} {t}", o, h, lo, c) for t, o, h, lo, c in rows], **kw)


def run(df, **kw):
    kw.setdefault("instrument", TOY)
    kw.setdefault("slippage_ticks", 0)
    kw.setdefault("atr_stop_mult", 1.0)
    kw.setdefault("risk_reward", 2.0)
    return run_backtest(df, **kw)


def test_long_target_entra_na_abertura_seguinte():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 125, 99, 120), signals={0: 1})
    t, m = run(df)
    assert len(t) == 1
    tr = t.iloc[0]
    assert tr.entry_price == 100 and tr.exit_price == 120 and tr.reason == "target"
    assert tr.entry_time == df.datetime[1]  # nao entra no proprio candle do sinal
    assert tr.pnl_brl == pytest.approx(20)
    assert m["n_trades"] == 1


def test_long_stop_paga_slippage_no_stop_mas_nao_no_alvo():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 105, 85, 90), signals={0: 1})
    t, _ = run(df, slippage_ticks=1)
    # entrada efetiva 101, stop 90 -> saida efetiva 89
    assert t.iloc[0].reason == "stop"
    assert t.iloc[0].pnl_points == pytest.approx(89 - 101)

    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 125, 99, 120), signals={0: 1})
    t, _ = run(df, slippage_ticks=1)
    # alvo e ordem limitada: so a entrada paga slippage
    assert t.iloc[0].pnl_points == pytest.approx(120 - 101)


def test_stop_e_alvo_na_mesma_barra_assume_stop():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 125, 85, 100), signals={0: 1})
    t, _ = run(df)
    assert t.iloc[0].reason == "stop" and t.iloc[0].pnl_brl == pytest.approx(-10)


def test_gap_alem_do_stop_sai_na_abertura():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 105, 95, 100),
              ("10:10", 80, 82, 78, 79), signals={0: 1})
    t, _ = run(df)
    assert t.iloc[0].reason == "stop_gap" and t.iloc[0].exit_price == 80
    assert t.iloc[0].pnl_brl == pytest.approx(-20)  # pior que o stop de -10


def test_gap_a_favor_do_alvo_sai_na_abertura():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 105, 95, 100),
              ("10:10", 130, 131, 128, 129), signals={0: 1})
    t, _ = run(df)
    assert t.iloc[0].reason == "target" and t.iloc[0].exit_price == 130


def test_short_simetrico():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 101, 75, 80), signals={0: -1})
    t, _ = run(df)
    tr = t.iloc[0]
    assert tr.side == "short" and tr.reason == "target" and tr.exit_price == 80
    assert tr.pnl_brl == pytest.approx(20)


def test_modo_legado_entra_no_fechamento_do_sinal():
    df = bars(("10:00", 100, 101, 99, 103), ("10:05", 103, 130, 102, 120), signals={0: 1})
    t, _ = run(df, entry="close")
    assert t.iloc[0].entry_price == 103 and t.iloc[0].entry_time == df.datetime[0]


def test_zeragem_forcada_no_horario():
    df = bars(("17:40", 100, 101, 99, 100), ("17:45", 100, 101, 99, 100),
              ("17:50", 104, 105, 103, 104), signals={0: 1})
    t, _ = run(df, force_flat="17:50")
    assert len(t) == 1 and t.iloc[0].reason == "eod" and t.iloc[0].exit_price == 104


def test_nao_entra_apos_horario_de_zeragem():
    df = bars(("17:45", 100, 101, 99, 100), ("17:50", 100, 130, 99, 120), signals={0: 1})
    t, m = run(df, force_flat="17:50")
    assert t.empty and m == {"n_trades": 0}


def test_posicao_nao_dorme_posicionada():
    rows = [(f"{D} 17:40", 100, 101, 99, 100), (f"{D} 17:45", 100, 101, 99, 100),
            ("2026-03-03 09:00", 104, 105, 103, 104)]
    t, _ = run(make_bars(rows, signals={0: 1}), force_flat=None)
    assert t.iloc[0].reason == "overnight" and t.iloc[0].exit_price == 104


def test_sinal_na_ultima_barra_do_dia_nao_entra_no_dia_seguinte():
    rows = [(f"{D} 17:45", 100, 101, 99, 100), ("2026-03-03 09:00", 100, 130, 99, 120)]
    t, _ = run(make_bars(rows, signals={0: 1}), force_flat=None)
    assert t.empty


def test_sinal_no_ultimo_candle_nao_gera_trade():
    t, _ = run(bars(("10:00", 100, 101, 99, 100), signals={0: 1}))
    assert t.empty


def test_uma_posicao_por_vez():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 105, 95, 100),
              ("10:10", 100, 105, 95, 100), signals={0: 1, 1: 1, 2: 1})
    t, _ = run(df, force_flat=None)
    assert len(t) <= 1


def test_taxa_do_instrumento_e_escala():
    df = bars(("10:00", 5000, 5001, 4999, 5000), ("10:05", 5000, 5030, 4999, 5025), signals={0: 1})
    kw = dict(instrument=WIN, slippage_ticks=0, atr_stop_mult=1.0, risk_reward=2.0)
    base, _ = run_backtest(df.assign(atr=5.0), **kw)
    dobro, _ = run_backtest(df.assign(atr=5.0), fee_scale=2.0, **kw)
    assert base.pnl_brl.iloc[0] - dobro.pnl_brl.iloc[0] == pytest.approx(WIN.fee_round_trip)


def test_entry_invalido():
    with pytest.raises(ValueError):
        run(bars(("10:00", 1, 1, 1, 1)), entry="foo")


def test_equity_acumula():
    rows = [(f"{D} 10:00", 100, 101, 99, 100), (f"{D} 10:05", 100, 125, 99, 120),
            (f"{D} 10:10", 120, 121, 119, 120), (f"{D} 10:15", 120, 121, 94, 100)]
    t, _ = run(make_bars(rows, signals={0: 1, 2: 1}))
    assert np.allclose(t.equity_brl, t.pnl_brl.cumsum())


def test_stop_fixo_em_pontos_via_stop_col():
    df = bars(("10:00", 100, 101, 99, 100), ("10:05", 100, 125, 99, 120), signals={0: 1})
    df["atr"] = float("nan")  # o ATR nao pode ser usado quando stop_col e dado
    df["stop_pts"] = 10.0
    t, _ = run(df, stop_col="stop_pts")
    assert t.iloc[0].reason == "target" and t.iloc[0].pnl_brl == pytest.approx(20)
