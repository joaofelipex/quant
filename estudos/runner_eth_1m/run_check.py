"""Checagem: a estrategia do runner ao vivo (trend_follow, ETH 1 min, stop 2 ATR, 24 h) da lucro depois de custos?

    python estudos/runner_eth_1m/run_check.py   # precisa de dados/raw/binance/ETHUSDT_1m.csv (fetch_binance)

Custo: 7 bps por lado. O motor tem alvo e o runner nao: rr=2 e rr=50 (praticamente so o stop) delimitam o caso.
"""
import pandas as pd

from quant.backtest.engine import run_backtest
from quant.instruments import Instrument
from quant.strategies import trend_follow as tf

PERIODOS = (("2023", "2023-01-01", "2024-01-01"), ("2024", "2024-01-01", "2025-01-01"),
            ("2025", "2025-01-01", "2025-11-01"))


def main() -> None:
    df = pd.read_csv("dados/raw/binance/ETHUSDT_1m.csv", parse_dates=["datetime"])
    df["datetime"] = df["datetime"].dt.tz_localize(None)
    for label, lo, hi in PERIODOS:
        d = df[(df.datetime >= lo) & (df.datetime < hi)].reset_index(drop=True)
        sig = tf.generate_signals(tf.add_indicators(d), session_start="00:00", session_end="23:59")
        eth = Instrument("ETH", point_value=1.0, tick_size=0.01, fee_round_trip=d["close"].mean() * 0.0014)
        for rr in (2.0, 50.0):
            trades, m = run_backtest(sig, atr_stop_mult=2.0, risk_reward=rr, instrument=eth, slippage_ticks=0,
                                     force_flat=None)
            pf = m.get("profit_factor", float("nan"))
            print(label, f"rr={rr}", "trades", len(trades), "pnl_usd/ETH", round(trades.pnl_brl.sum(), 1),
                  "PF", round(pf, 2))


if __name__ == "__main__":
    main()
