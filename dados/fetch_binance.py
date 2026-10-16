"""Baixa klines mensais da Binance (data.binance.vision) e grava um CSV por simbolo.

Uso:
    python dados/fetch_binance.py BTCUSDT 1m 2023-01 2024-12
    python dados/fetch_binance.py ETHUSDT 5m 2024-01        # so um mes
Saida: dados/raw/binance/<SIMBOLO>_<intervalo>.csv (datetime UTC, OHLCV, trades, taker_buy_base)
"""
import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BASE = "https://data.binance.vision/data/spot/monthly/klines"
OUT_DIR = Path(__file__).resolve().parent / "raw" / "binance"
COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]


def month_range(start: str, end: str):
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def fetch_month(symbol: str, interval: str, month: str) -> pd.DataFrame | None:
    url = f"{BASE}/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    try:
        raw = urllib.request.urlopen(url, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f, header=None, names=COLS)
    # alguns arquivos trazem linha de cabecalho
    df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()].copy()
    df["open_time"] = df["open_time"].astype("int64")
    # a partir de 2025 o spot usa microssegundos
    unit = "us" if df["open_time"].iloc[0] > 10**14 else "ms"
    df["datetime"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    keep = ["datetime", "open", "high", "low", "close", "volume", "trades", "taker_buy_base"]
    return df[keep]


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    symbol, interval, start = sys.argv[1].upper(), sys.argv[2], sys.argv[3]
    end = sys.argv[4] if len(sys.argv) > 4 else start

    frames = []
    for month in month_range(start, end):
        df = fetch_month(symbol, interval, month)
        print(f"{symbol} {interval} {month}: {'indisponivel' if df is None else f'{len(df)} candles'}")
        if df is not None:
            frames.append(df)
    if not frames:
        sys.exit("Nenhum dado baixado.")

    out = pd.concat(frames).drop_duplicates("datetime").sort_values("datetime")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{symbol}_{interval}.csv"
    out.to_csv(path, index=False)
    print(f"\n{len(out)} candles, {out['datetime'].min()} a {out['datetime'].max()}\nSalvo em {path}")


if __name__ == "__main__":
    main()
