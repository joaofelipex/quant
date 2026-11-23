"""Baixa o funding rate historico dos perpetuos USD-M (data.binance.vision) e grava um CSV por simbolo.

Uso:
    python -m quant.data.fetch_funding BTCUSDT 2020-01 2025-10
Saida: dados/raw/binance/<SIMBOLO>_funding.csv (datetime UTC, funding_rate por periodo de 8 h;
positivo = long paga short)
"""
import io
import sys
import urllib.error
import urllib.request
import zipfile

import pandas as pd

from quant.data.fetch_binance import OUT_DIR, month_range

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"


def fetch_month(symbol: str, month: str) -> pd.DataFrame | None:
    url = f"{BASE}/{symbol}/{symbol}-fundingRate-{month}.zip"
    try:
        raw = urllib.request.urlopen(url, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(raw)) as z, z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f)
    df["datetime"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True).dt.round("s")
    return df.rename(columns={"last_funding_rate": "funding_rate"})[["datetime", "funding_rate"]]


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    symbol, start, end = sys.argv[1].upper(), sys.argv[2], sys.argv[3]
    frames = [f for m in month_range(start, end) if (f := fetch_month(symbol, m)) is not None]
    if not frames:
        sys.exit("Nenhum dado baixado.")
    out = pd.concat(frames).drop_duplicates("datetime").sort_values("datetime")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{symbol}_funding.csv"
    out.to_csv(path, index=False)
    print(f"{symbol}: {len(out)} registros, {out['datetime'].min()} a {out['datetime'].max()}")


if __name__ == "__main__":
    main()
