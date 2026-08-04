"""
Analisa relatório de deals do MetaTrader 5 (CSV exportado do Strategy Tester
ou da aba Histórico).

Como exportar no MT5:
  1. Strategy Tester → aba Results / Deals
  2. Clique direito → Report → Open XML  (ou salve CSV via histórico)
  3. Ou: Conta → Histórico → clique direito → Relatório → CSV
  4. Coloque o arquivo em python/data/  e rode:

     pip install -r requirements.txt
     python analyze_trades.py data/seu_arquivo.csv

Aceita CSV com colunas comuns do MT5 (Time, Type, Profit, ...) em PT/EN.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPORTS = Path(__file__).resolve().parent / "reports"


# nomes possíveis de colunas (EN / PT / variações do export)
COL_ALIASES = {
    "time": ["time", "tempo", "open time", "hora", "datetime", "date"],
    "type": ["type", "tipo", "direction", "direção", "direcao"],
    "profit": ["profit", "lucro", "profit/loss", "p/l", "pl"],
    "symbol": ["symbol", "símbolo", "simbolo", "instrumento"],
    "volume": ["volume", "vol", "lots", "lotes"],
    "commission": ["commission", "comissão", "comissao"],
    "swap": ["swap", "overnight"],
}


def _norm(s: str) -> str:
    return (
        str(s)
        .strip()
        .lower()
        .replace("\ufeff", "")
        .replace("/", " ")
    )


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    cols = {_norm(c): c for c in df.columns}
    for canonical, aliases in COL_ALIASES.items():
        for alias in aliases:
            if alias in cols:
                mapping[cols[alias]] = canonical
                break
    out = df.rename(columns=mapping)
    missing = [k for k in ("time", "profit") if k not in out.columns]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias não encontradas: {missing}. "
            f"Colunas no arquivo: {list(df.columns)}"
        )
    return out


def load_trades(path: Path) -> pd.DataFrame:
    # tenta separadores comuns do export MT5
    last_err: Exception | None = None
    for sep in (",", ";", "\t"):
        try:
            df = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
            if df.shape[1] == 1:
                continue
            df = map_columns(df)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            df = None  # type: ignore
    else:
        raise SystemExit(f"Não foi possível ler CSV: {last_err}")

    df["time"] = pd.to_datetime(df["time"], errors="coerce", dayfirst=True)
    df["profit"] = pd.to_numeric(df["profit"], errors="coerce")
    for opt in ("commission", "swap"):
        if opt in df.columns:
            df[opt] = pd.to_numeric(df[opt], errors="coerce").fillna(0.0)
        else:
            df[opt] = 0.0

    # filtra linhas de deal com P/L (ignora balance/credit se type existir)
    if "type" in df.columns:
        t = df["type"].astype(str).str.lower()
        keep = t.str.contains("buy|sell|in|out|buy|sell|compra|venda", regex=True)
        # se filtro zerar tudo, mantém linhas com profit não-nulo
        if keep.any():
            df = df.loc[keep | df["profit"].notna()]

    df = df.dropna(subset=["time", "profit"]).sort_values("time").reset_index(drop=True)
    df["net"] = df["profit"] + df["commission"] + df["swap"]
    df["equity"] = df["net"].cumsum()
    return df


def metrics(df: pd.DataFrame) -> dict:
    net = df["net"].to_numpy()
    if len(net) == 0:
        return {"trades": 0}

    wins = net[net > 0]
    losses = net[net < 0]
    equity = df["equity"].to_numpy()
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) else 0.0

    profit_factor = (
        float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.inf
    )
    win_rate = float(len(wins) / len(net)) if len(net) else 0.0
    expectancy = float(net.mean())

    return {
        "trades": int(len(net)),
        "net_pnl": float(net.sum()),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "max_drawdown": max_dd,
        "best_trade": float(net.max()),
        "worst_trade": float(net.min()),
    }


def print_report(m: dict) -> None:
    print("\n=== PERFORMANCE ===")
    print(f"Trades        : {m['trades']}")
    if m["trades"] == 0:
        return
    print(f"Net P&L       : {m['net_pnl']:.2f}")
    print(f"Win rate      : {m['win_rate']*100:.1f}%")
    pf = m["profit_factor"]
    print(f"Profit factor : {'inf' if np.isinf(pf) else f'{pf:.2f}'}")
    print(f"Expectancy    : {m['expectancy']:.2f}")
    print(f"Avg win/loss  : {m['avg_win']:.2f} / {m['avg_loss']:.2f}")
    print(f"Max drawdown  : {m['max_drawdown']:.2f}")
    print(f"Best / Worst  : {m['best_trade']:.2f} / {m['worst_trade']:.2f}")


def plot_equity(df: pd.DataFrame, out: Path) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    axes[0].plot(df["time"], df["equity"], color="#1f4e79", lw=1.6)
    axes[0].axhline(0, color="#999", lw=0.8)
    axes[0].set_title("Equity curve (net)")
    axes[0].set_ylabel("Cumulative P&L")

    axes[1].bar(
        df["time"],
        df["net"],
        width=0.02,
        color=["#2ca02c" if x >= 0 else "#d62728" for x in df["net"]],
    )
    axes[1].set_title("Trade P&L")
    axes[1].set_ylabel("Net")
    axes[1].set_xlabel("Time")

    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"Gráfico salvo: {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analisa trades MT5 (CSV)")
    parser.add_argument("csv", type=Path, help="Caminho do CSV exportado")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="PNG de saída (default: reports/equity_<nome>.png)",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Arquivo não encontrado: {args.csv}", file=sys.stderr)
        return 1

    df = load_trades(args.csv)
    m = metrics(df)
    print_report(m)

    out = args.out or (REPORTS / f"equity_{args.csv.stem}.png")
    if m["trades"] > 0:
        plot_equity(df, out)
        summary_path = REPORTS / f"summary_{args.csv.stem}.csv"
        pd.DataFrame([m]).to_csv(summary_path, index=False)
        print(f"Resumo CSV   : {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
