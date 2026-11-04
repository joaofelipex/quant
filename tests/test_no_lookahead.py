"""Regressao anti-look-ahead: truncar o futuro nao pode mudar sinais ja emitidos."""
import pandas as pd
import pytest

from quant.strategies.trend_follow import add_indicators, generate_signals


def signals(df):
    return generate_signals(add_indicators(df), er_threshold=0.2)


@pytest.mark.parametrize("cut", [150, 230, 300, 380])
def test_sinais_passados_nao_dependem_do_futuro(random_walk_bars, cut):
    full = signals(random_walk_bars)
    part = signals(random_walk_bars.iloc[:cut].copy())
    cols = ["ema_fast", "ema_slow", "atr", "donchian_high", "donchian_low", "er", "signal"]
    pd.testing.assert_frame_equal(
        full.iloc[:cut][cols].reset_index(drop=True), part[cols].reset_index(drop=True)
    )


def test_gera_alguns_sinais_de_ambos_os_lados(random_walk_bars):
    s = signals(random_walk_bars).signal
    assert (s == 1).any() and (s == -1).any()  # o teste acima nao pode passar "por vacuidade"


def test_ema_macd_sem_lookahead(random_walk_bars):
    from quant.strategies import ema_macd

    def sig(df):
        return ema_macd.generate_signals(ema_macd.add_indicators(df))

    full = sig(random_walk_bars)
    for cut in (150, 230, 300):
        part = sig(random_walk_bars.iloc[:cut].copy())
        pd.testing.assert_series_equal(
            full.signal.iloc[:cut].reset_index(drop=True), part.signal.reset_index(drop=True)
        )
    assert (full.signal != 0).any()
