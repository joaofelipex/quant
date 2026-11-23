import numpy as np
import pandas as pd

from quant.ml.features import FEATURES, forward_return, make_features


def _bars(n=400, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"datetime": pd.date_range("2024-01-01", periods=n, freq="h")})
    df["open"] = np.r_[close[0], close[:-1]]
    df["close"] = close
    df["high"] = np.maximum(df["open"], df["close"]) * 1.002
    df["low"] = np.minimum(df["open"], df["close"]) * 0.998
    df["volume"] = rng.uniform(50, 150, n)
    df["taker_buy_base"] = df["volume"] * rng.uniform(0.3, 0.7, n)
    return df


def test_features_sao_causais():
    """A feature da barra t nao muda se apagarmos todo o futuro: truncar em t e recalcular da o mesmo valor."""
    df = _bars()
    full = make_features(df)
    for t in (200, 300, 399):
        cut = make_features(df.iloc[: t + 1].copy())
        pd.testing.assert_series_equal(full.iloc[t], cut.iloc[t], check_names=False)


def test_forward_return_entra_na_abertura_seguinte():
    df = _bars(20)
    fr = forward_return(df, horizon=4)
    assert fr.iloc[0] == df["open"].iloc[5] / df["open"].iloc[1] - 1
    assert fr.iloc[-5:].isna().all()  # sem futuro => sem rotulo


def test_colunas():
    assert list(make_features(_bars())) == FEATURES
