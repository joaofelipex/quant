"""Estudo trend_eth_tf: o trend_follow do runner em ETH 15m/1h/4h (ver README: desenho pre-registrado e fixo).

    python estudos/trend_eth_tf/run_study.py        # precisa de dados/raw/binance/ETHUSDT_1m.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant.backtest.engine import run_backtest
from quant.instruments import Instrument
from quant.strategies import trend_follow as tf
from quant.validation import deflated_sharpe_ratio

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent / "reports"
DEV, HOLD, END = ("2023-01-01", "2024-07-01"), ("2024-07-01", "2025-11-01"), None
PRIMARY, ROBUST = "1h", ("15min", "4h")
N_TRIALS = 38
COST_SIDE = 0.0007


def bars(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    d = df.set_index("datetime").resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return d.reset_index()


def backtest(df: pd.DataFrame, rule: str, lo: str, hi: str, cost_scale: float = 1.0):
    d = df[(df.datetime >= lo) & (df.datetime < hi)]
    b = bars(d, rule)
    sig = tf.generate_signals(tf.add_indicators(b), session_start="00:00", session_end="23:59")
    eth = Instrument("ETH", point_value=1.0, tick_size=0.01, fee_round_trip=b["close"].mean() * 2 * COST_SIDE)
    return run_backtest(sig, atr_stop_mult=2.0, risk_reward=50.0, instrument=eth, slippage_ticks=0, force_flat=None,
                        fee_scale=cost_scale)


def quarters(trades: pd.DataFrame) -> list[tuple[str, int, float]]:
    q = trades.groupby(pd.to_datetime(trades["exit_time"]).dt.to_period("Q"))["pnl_brl"]
    return [(str(k), int(len(v)), float(v.sum())) for k, v in q]


def main() -> None:
    df = pd.read_csv(ROOT / "dados/raw/binance/ETHUSDT_1m.csv", parse_dates=["datetime"])
    df["datetime"] = df["datetime"].dt.tz_localize(None)
    rows, out = [], {}
    for rule in (PRIMARY, *ROBUST):
        for name, (lo, hi) in (("dev", DEV), ("holdout", HOLD)):
            t, m = backtest(df, rule, lo, hi)
            rows.append({"tf": rule, "periodo": name, "trades": m["n_trades"], "pnl_usd_por_eth": m["gross_pnl_brl"],
                         "pf": m["profit_factor"], "t_stat": m["t_stat"]})
            out[(rule, name)] = t
    table = pd.DataFrame(rows).set_index(["tf", "periodo"])
    t_h, m_h = backtest(df, PRIMARY, *HOLD)
    _, m_x2 = backtest(df, PRIMARY, *HOLD, cost_scale=2.0)
    dsr = deflated_sharpe_ratio(t_h["pnl_brl"], N_TRIALS) if len(t_h) > 2 else float("nan")
    qs = quarters(t_h)
    pos_q = sum(1 for _, n, p in qs if n >= 20 and p > 0)
    ok = [m_h["profit_factor"] > 1.2 and m_h["t_stat"] > 2, dsr >= 0.95, m_x2["profit_factor"] > 1, pos_q >= 2]
    names = ["1. PF > 1,2 e t-stat > 2", "2. DSR >= 0,95 (N_TRIALS=38)", "3. PF > 1 com custo x2",
             "4. >= 2 trimestres positivos com >= 20 trades"]
    lines = [f"# trend_eth_tf - resultados\n\n## Veredito: **{'APROVADA' if all(ok) else 'REPROVADA'}**"]
    lines += [f"- [{'x' if o else ' '}] {n}" for o, n in zip(ok, names, strict=True)]
    lines += ["\n## Todas as variantes", "```\n" + table.round(2).to_string() + "\n```",
              f"\nPrimaria (1h) hold-out: DSR {dsr:.3f}; PF com custo x2 = {m_x2['profit_factor']:.2f}.",
              "\n## Trimestres do hold-out (1h): periodo, trades, pnl USD por ETH",
              "```\n" + "\n".join(f"{q} {n:4d} {p:10.1f}" for q, n, p in qs) + "\n```"]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "resultados.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
