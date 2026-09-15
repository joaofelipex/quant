"""Estrategia de tendencia para WIN: EMA filter + rompimento de canal (Donchian) + stop/alvo por ATR."""
import pandas as pd
import numpy as np


def load_win_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", header=0, names=["datetime", "open", "high", "low", "close"])
    df["datetime"] = pd.to_datetime(df["datetime"], format="%d/%m/%Y %H:%M")
    df = df.sort_values("datetime").drop_duplicates(subset="datetime").reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame, ema_fast=9, ema_slow=21, atr_period=14, donchian_period=20, er_period=20) -> pd.DataFrame:
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

    df["time"] = df["datetime"].dt.time
    return df


def generate_signals(df: pd.DataFrame, session_start="09:15", session_end="17:45", er_threshold=0.5) -> pd.DataFrame:
    df = df.copy()
    start = pd.to_datetime(session_start).time()
    end = pd.to_datetime(session_end).time()
    in_session = (df["time"] >= start) & (df["time"] <= end)

    trend_up = df["ema_fast"] > df["ema_slow"]
    trend_down = df["ema_fast"] < df["ema_slow"]
    trending_regime = df["er"] >= er_threshold

    long_entry = in_session & trending_regime & trend_up & (df["close"] > df["donchian_high"])
    short_entry = in_session & trending_regime & trend_down & (df["close"] < df["donchian_low"])

    df["signal"] = 0
    df.loc[long_entry, "signal"] = 1
    df.loc[short_entry, "signal"] = -1
    return df
