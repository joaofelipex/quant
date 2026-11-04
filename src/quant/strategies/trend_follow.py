"""Tendencia intradiaria: filtro EMA + regime ER (Kaufman) + rompimento Donchian; stop/alvo por ATR.

Todos os indicadores sao causais (barra *t* so usa dados ate *t*); o canal Donchian e deslocado em 1
barra para que o rompimento seja medido contra o canal anterior. Teste de regressao em
``tests/test_no_lookahead.py``.
"""
import pandas as pd


def add_indicators(
    df: pd.DataFrame, ema_fast=9, ema_slow=21, atr_period=14, donchian_period=20, er_period=20
) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()

    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=atr_period, adjust=False).mean()

    df["donchian_high"] = df["high"].rolling(donchian_period).max().shift(1)
    df["donchian_low"] = df["low"].rolling(donchian_period).min().shift(1)

    # Efficiency Ratio (Kaufman): 1 = tendencia pura, 0 = ruido puro
    net_change = (df["close"] - df["close"].shift(er_period)).abs()
    path_length = df["close"].diff().abs().rolling(er_period).sum()
    df["er"] = net_change / path_length

    return df


def generate_signals(df: pd.DataFrame, session_start="09:15", session_end="17:45", er_threshold=0.5) -> pd.DataFrame:
    df = df.copy()
    start = pd.to_datetime(session_start).time()
    end = pd.to_datetime(session_end).time()
    bar_time = df["datetime"].dt.time
    in_session = (bar_time >= start) & (bar_time <= end)

    trend_up = df["ema_fast"] > df["ema_slow"]
    trend_down = df["ema_fast"] < df["ema_slow"]
    trending_regime = df["er"] >= er_threshold

    long_entry = in_session & trending_regime & trend_up & (df["close"] > df["donchian_high"])
    short_entry = in_session & trending_regime & trend_down & (df["close"] < df["donchian_low"])

    df["signal"] = 0
    df.loc[long_entry, "signal"] = 1
    df.loc[short_entry, "signal"] = -1
    return df
