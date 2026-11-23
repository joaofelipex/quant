"""Carga e saneamento de barras OHLC.

Um unico ponto de entrada para os exports do Profit (CSV ou XLSX, decimal com virgula,
data dd/mm/aaaa) e para o formato canonico do repo (``datetime,open,high,low,close``).
Todo o resto do pacote assume o DataFrame canonico devolvido aqui.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OHLC = ["open", "high", "low", "close"]
CANONICAL = ["datetime", *OHLC]


def _to_float(series: pd.Series) -> pd.Series:
    """'5.099,50' -> 5099.5 ; '5099,50' -> 5099.5 ; '5099.5' -> 5099.5 ; numeros passam direto."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    s = series.astype(str).str.strip()
    has_comma = s.str.contains(",", regex=False)
    s = s.where(~has_comma, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def _to_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):  # serial do Excel (dias desde 1899-12-30)
        dt = pd.Timestamp("1899-12-30") + pd.to_timedelta(series.astype(float), unit="D")
        return dt.dt.round("s")
    s = series.astype(str).str.strip()
    if s.str.match(r"^\d{4}-\d{2}-\d{2}").all():  # ISO: NUNCA com dayfirst (pandas novo troca mes e dia)
        return pd.to_datetime(s, format="ISO8601")
    return pd.to_datetime(s, dayfirst=True, format="mixed")  # export do Profit: dd/mm/aaaa hh:mm


def _read_raw(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            return pd.read_excel(path, header=0)
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise ImportError("ler .xlsx requer openpyxl: pip install 'quant[excel]'") from exc
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"nao consegui decodificar {path}")


def load_bars(path: str | Path, min_bars_per_day: int | None = None) -> pd.DataFrame:
    """Le barras OHLC e devolve DataFrame canonico, ordenado, sem duplicatas.

    ``min_bars_per_day`` remove dias com poucas barras (contrato ilíquido / vencimento antigo
    exportado esparso); ver ``drop_illiquid_days``.
    """
    path = Path(path)
    raw = _read_raw(path)
    raw.columns = [str(c).strip().lower() for c in raw.columns]

    if "datetime" in raw.columns and all(c in raw.columns for c in OHLC):
        df = raw[CANONICAL].copy()
    else:
        if raw.shape[1] < 5:
            raise ValueError(f"{path.name}: esperava 5 colunas (data, abertura, maxima, minima, fechamento)")
        df = raw.iloc[:, :5].copy()
        df.columns = CANONICAL

    df["datetime"] = _to_datetime(df["datetime"])
    for col in OHLC:
        df[col] = _to_float(df[col])

    df = df.dropna(subset=CANONICAL)
    df = df.sort_values("datetime").drop_duplicates(subset="datetime", keep="last").reset_index(drop=True)
    if min_bars_per_day:
        df = drop_illiquid_days(df, min_bars_per_day)
    return df


def drop_illiquid_days(df: pd.DataFrame, min_bars: int) -> pd.DataFrame:
    """Remove dias com menos de ``min_bars`` barras. Indicadores sobre barras esparsas mentem."""
    n = df.groupby(df["datetime"].dt.date)["datetime"].transform("size")
    return df[n >= min_bars].reset_index(drop=True)


def check_bars(df: pd.DataFrame) -> dict:
    """Diagnostico de qualidade: ranges invalidos, saltos grandes e dias esparsos."""
    bad_range = int(((df["high"] < df[["open", "close", "low"]].max(axis=1))
                     | (df["low"] > df[["open", "close", "high"]].min(axis=1))).sum())
    per_day = df.groupby(df["datetime"].dt.date).size()
    gap = df["close"].pct_change().abs()
    return {
        "n_bars": len(df),
        "first": df["datetime"].min(),
        "last": df["datetime"].max(),
        "invalid_ohlc": bad_range,
        "median_bars_per_day": float(per_day.median()) if len(per_day) else 0.0,
        "sparse_days": int((per_day < 0.5 * per_day.median()).sum()) if len(per_day) else 0,
        "max_abs_return": float(gap.max()) if len(df) > 1 else 0.0,
        "n_jumps_gt_2pct": int((gap > 0.02).sum()),
    }


def save_bars(df: pd.DataFrame, path: str | Path) -> None:
    """Grava no formato canonico (ISO, ponto decimal), estavel para versionar no git."""
    out = df[CANONICAL].copy()
    out["datetime"] = out["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(path, index=False)
