import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.trend_follow import load_win_csv, add_indicators, generate_signals
from backtest.engine import run_backtest

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "win_5min_raw.csv"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def plot_equity_curve(trades_df, out_path):
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(trades_df["exit_time"], trades_df["equity_brl"], color="#2563eb", linewidth=1.5)
    ax.axhline(0, color="#999999", linewidth=0.8, linestyle="--")

    running_max = trades_df["equity_brl"].cummax()
    ax.fill_between(
        trades_df["exit_time"], trades_df["equity_brl"], running_max,
        where=trades_df["equity_brl"] < running_max, color="#dc2626", alpha=0.15,
        label="drawdown",
    )

    ax.set_title("Curva de capital — estrategia tendencia WIN (5min, liquido de custos)")
    ax.set_xlabel("Data")
    ax.set_ylabel("Capital acumulado (R$)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main():
    df = load_win_csv(DATA_PATH)
    df = add_indicators(df)
    df = generate_signals(df)

    trades_df, metrics = run_backtest(
        df, atr_stop_mult=1.5, risk_reward=2.0, contracts=1,
        slippage_ticks=1, fee_brl_round_trip=1.20,
    )

    print(f"Periodo: {df['datetime'].min()} a {df['datetime'].max()}")
    print(f"Candles: {len(df)}")
    print("---")
    for k, v in metrics.items():
        print(f"{k}: {v}")

    trades_path = REPORTS_DIR / "trades.csv"
    trades_df.to_csv(trades_path, index=False)
    print(f"\nTrades salvos em {trades_path}")

    if not trades_df.empty:
        equity_path = REPORTS_DIR / "equity_curve.png"
        plot_equity_curve(trades_df, equity_path)
        print(f"Curva de capital salva em {equity_path}")


if __name__ == "__main__":
    main()
