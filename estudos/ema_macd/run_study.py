"""Estudo ema_macd: a linha de robos NTSL v11-v14 (cruzamento EMA + MACD) sob o motor realista.

    python estudos/ema_macd/run_study.py

Compara variantes em WIN (duas series) e WDO. Nada e otimizado aqui: stops/alvos sao os dos robos.
Cada linha da tabela e uma "tentativa" para efeito de Sharpe deflacionado (ver N_TRIALS no README).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.backtest.engine import run_backtest
from quant.data.loaders import load_bars
from quant.instruments import WDO, WIN
from quant.strategies import ema_macd
from quant.validation import bootstrap_trades, deflated_sharpe_ratio

ROOT = Path(__file__).resolve().parents[2]
CURATED = ROOT / "dados" / "curated"
REPORTS = Path(__file__).resolve().parent / "reports"

# (rotulo, arquivo, instrumento, stop em pontos, filtro de tendencia lenta)
CASES = [
    ("WIN prev | v10-like sem filtro 300/600", "win_prev_5min.csv", WIN, 300, False),
    ("WIN prev | v11 filtro lento 300/600", "win_prev_5min.csv", WIN, 300, True),
    ("WIN z26  | sem filtro 300/600", "win_z26_5min.csv", WIN, 300, False),
    ("WIN z26  | v11 filtro lento 300/600", "win_z26_5min.csv", WIN, 300, True),
    ("WIN z26  | v11 filtro lento 400/800", "win_z26_5min.csv", WIN, 400, True),
    ("WDO      | sem filtro 8/16", "wdo_5min.csv", WDO, 8, False),
    ("WDO      | filtro lento 8/16", "wdo_5min.csv", WDO, 8, True),
    ("WDO      | filtro lento 15/30", "wdo_5min.csv", WDO, 15, True),
]
MIN_BARS = 60
N_TRIALS = len(CASES)


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    rows = []
    for label, fname, instrument, stop, use_filter in CASES:
        df = load_bars(CURATED / fname, min_bars_per_day=MIN_BARS)
        sig = ema_macd.generate_signals(ema_macd.add_indicators(df), use_trend_filter=use_filter, stop_points=stop)
        trades, m = run_backtest(sig, stop_col="stop_dist", risk_reward=2.0, slippage_ticks=1,
                                 instrument=instrument, force_flat="17:50")
        row = {"caso": label, "dias": int(df.datetime.dt.date.nunique())}
        if trades.empty:
            rows.append(row | {"trades": 0})
            continue
        pnl = trades["pnl_brl"]
        b = bootstrap_trades(pnl)
        rows.append(row | {
            "trades": m["n_trades"], "win_rate": round(m["win_rate"], 2), "pf": round(m["profit_factor"], 2),
            "pnl_brl": round(m["gross_pnl_brl"], 0), "dd_brl": round(m["max_drawdown_brl"], 0),
            "t_stat": round(m["t_stat"], 2), "p_prejuizo": round(b["prob_loss"], 2),
            "dsr": round(deflated_sharpe_ratio(pnl, N_TRIALS), 3),
        })
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    table.to_csv(REPORTS / "variantes.csv", index=False)
    out = json.dumps(rows, indent=2, ensure_ascii=False, default=float)
    (REPORTS / "variantes.json").write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
