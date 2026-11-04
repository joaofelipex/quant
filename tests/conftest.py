import numpy as np
import pandas as pd
import pytest

from quant.instruments import Instrument

# contrato "de brinquedo": 1 ponto = 1 moeda, tick = 1 ponto, sem taxa -> contas feitas de cabeca
TOY = Instrument("TOY", point_value=1.0, tick_size=1.0, fee_round_trip=0.0)


def make_bars(rows, signals=None, atr=10.0):
    """rows: [("2026-03-02 10:00", o, h, l, c), ...]; signals: {indice_da_barra: +1/-1}."""
    df = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["signal"] = 0
    for i, s in (signals or {}).items():
        df.loc[i, "signal"] = s
    df["atr"] = atr
    return df


@pytest.fixture
def toy():
    return TOY


@pytest.fixture(scope="session")
def random_walk_bars():
    """Quatro dias de barras de 5 min (09:00-17:55) de um passeio aleatorio reprodutivel."""
    rng = np.random.default_rng(42)
    idx = pd.DatetimeIndex([])
    for day in pd.bdate_range("2026-03-02", periods=4):
        start = day + pd.Timedelta(hours=9)
        end = day + pd.Timedelta(hours=17, minutes=55)
        idx = idx.append(pd.date_range(start, end, freq="5min"))
    close = 100_000 + np.cumsum(rng.normal(0, 40, len(idx)))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 25, len(idx)))
    return pd.DataFrame({
        "datetime": idx, "open": open_, "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread, "close": close,
    })
