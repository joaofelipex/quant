"""Cruzamento de EMAs confirmado por MACD, com filtro opcional de tendencia lenta e stop fixo em pontos.

Equivalente em Python da linha NTSL ``WinTrendBot_v11``-``v14`` (``execucao/profitpro``): compra no cruzamento
EMA rapida > lenta com MACD > sinal; vende no inverso. O filtro de tendencia lenta (EMA 27/63 em 5 min,
aproximadamente EMA 9/21 em 15 min) so deixa operar a favor da tendencia maior.

Nao modelado aqui (existe nos robos): maximo de entradas/stops por dia e limite de perda diaria.
O MACD e EMA(fast)-EMA(slow) com sinal EMA; o ``macd()`` nativo do Profit pode diferir marginalmente.
"""
import pandas as pd


def add_indicators(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 21,
    macd: tuple[int, int, int] = (12, 26, 9),
    trend: tuple[int, int] = (27, 63),
) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["ema_fast"] = c.ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = c.ewm(span=ema_slow, adjust=False).mean()
    fast, slow, sig = macd
    df["macd"] = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    df["macd_signal"] = df["macd"].ewm(span=sig, adjust=False).mean()
    df["trend_fast"] = c.ewm(span=trend[0], adjust=False).mean()
    df["trend_slow"] = c.ewm(span=trend[1], adjust=False).mean()
    return df


def generate_signals(
    df: pd.DataFrame,
    use_trend_filter: bool = True,
    stop_points: float = 300.0,
    session_start: str = "09:15",
    session_end: str = "17:45",
) -> pd.DataFrame:
    """Marca ``signal`` (+1/-1/0) e ``stop_dist`` (pontos) para o motor (``stop_col='stop_dist'``)."""
    df = df.copy()
    prev_fast, prev_slow = df["ema_fast"].shift(1), df["ema_slow"].shift(1)
    cross_up = (prev_fast < prev_slow) & (df["ema_fast"] > df["ema_slow"]) & (df["macd"] > df["macd_signal"])
    cross_dn = (prev_fast > prev_slow) & (df["ema_fast"] < df["ema_slow"]) & (df["macd"] < df["macd_signal"])
    if use_trend_filter:
        cross_up &= df["trend_fast"] > df["trend_slow"]
        cross_dn &= df["trend_fast"] < df["trend_slow"]

    bar_time = df["datetime"].dt.time
    in_session = (bar_time >= pd.to_datetime(session_start).time()) & (bar_time <= pd.to_datetime(session_end).time())

    df["signal"] = 0
    df.loc[cross_up & in_session, "signal"] = 1
    df.loc[cross_dn & in_session, "signal"] = -1
    df["stop_dist"] = float(stop_points)
    return df
