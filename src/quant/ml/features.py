"""Features e rotulo para barras horarias de cripto.

Toda feature da barra *t* usa apenas dados ate o fechamento de *t* (causal); ``tests/test_ml_features.py``
garante isso truncando a serie. O rotulo, ao contrario, olha o futuro por construcao: so pode ser usado
para TREINAR, e as linhas de treino cujo rotulo invade o periodo de teste tem de ser purgadas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "r1", "r4", "r24", "r72", "vol24", "vol_ratio", "er24", "dist_ema24", "vol_z", "taker_ratio",
    "hour_sin", "hour_cos",
]


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """``df``: datetime, open, high, low, close, volume, taker_buy_base. Devolve so as colunas FEATURES."""
    c = df["close"]
    r1 = c.pct_change()
    out = pd.DataFrame(index=df.index)
    for k in (1, 4, 24, 72):
        out[f"r{k}"] = c.pct_change(k)
    out["vol24"] = r1.rolling(24).std()
    out["vol_ratio"] = out["vol24"] / r1.rolling(168).std()
    net = (c - c.shift(24)).abs()
    path = c.diff().abs().rolling(24).sum()
    out["er24"] = net / path  # eficiencia de Kaufman: 1 = tendencia pura
    out["dist_ema24"] = c / c.ewm(span=24, adjust=False).mean() - 1
    v = df["volume"]
    out["vol_z"] = (v - v.rolling(168).mean()) / v.rolling(168).std()
    out["taker_ratio"] = df["taker_buy_base"] / v  # fracao do volume com agressor comprador
    hour = df["datetime"].dt.hour
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    return out[FEATURES].replace([np.inf, -np.inf], np.nan)


def forward_return(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Retorno da abertura de t+1 (onde a ordem realmente entra) ate a abertura de t+1+horizon. So para treino."""
    o = df["open"]
    return o.shift(-(1 + horizon)) / o.shift(-1) - 1
