import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def main():
    df = pd.read_csv(REPORTS_DIR / "trades.csv", parse_dates=["entry_time", "exit_time"])
    df["month"] = df["exit_time"].dt.to_period("M").astype(str)

    monthly = df.groupby("month")["pnl_brl"].sum()
    colors = ["#16a34a" if v >= 0 else "#dc2626" for v in monthly.values]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(monthly.index, monthly.values, color=colors)
    ax.axhline(0, color="#666666", linewidth=0.8)
    ax.set_title("PnL liquido mensal — estrategia tendencia WIN")
    ax.set_ylabel("PnL (R$)")
    for i, v in enumerate(monthly.values):
        ax.text(i, v + (15 if v >= 0 else -25), f"R$ {v:,.0f}", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "monthly_pnl.png", dpi=140)
    plt.close(fig)
    print("Grafico salvo em", REPORTS_DIR / "monthly_pnl.png")


if __name__ == "__main__":
    main()
