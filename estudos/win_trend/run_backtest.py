"""Tearsheet do estudo win_trend: tendencia intradiaria no WIN (EMA + ER + Donchian, stop/alvo em ATR).

    python estudos/win_trend/run_backtest.py

Para cada serie: metricas liquidas de custo, sensibilidade a execucao (entrada na abertura seguinte x
no fechamento do sinal), estresse de custos, bootstrap dos trades, Sharpe deflacionado e PnL mensal.
As duas series sao CONTRATOS DIFERENTES (WIN anterior x WINZ26) e cobrem periodos que se sobrepoem:
nao sao amostras independentes e nunca devem ser concatenadas.
"""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from quant.backtest.engine import run_backtest  # noqa: E402
from quant.data.loaders import load_bars  # noqa: E402
from quant.instruments import WIN  # noqa: E402
from quant.strategies.trend_follow import add_indicators, generate_signals  # noqa: E402
from quant.validation import bootstrap_trades, deflated_sharpe_ratio, stress_costs, train_test_split_time  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CURATED = ROOT / "dados" / "curated"
REPORTS = Path(__file__).resolve().parent / "reports"

# Parametros fixados no README original (nada foi reotimizado para este relatorio).
PARAMS = dict(ema_fast=9, ema_slow=21, atr_period=14, donchian_period=20, er_period=20)
SIGNAL = dict(session_start="09:15", session_end="17:45", er_threshold=0.5)
RUN = dict(atr_stop_mult=1.5, risk_reward=2.0, contracts=1, slippage_ticks=1, instrument=WIN, force_flat="17:50")

MIN_BARS_PER_DAY = 60  # dias com menos barras de 5 min sao contrato iliquido; indicadores nao valem
TRAIN_END = "2026-08-01"  # corte treino/teste da serie anterior, definido antes dos novos dados
# Numero de variantes/parametros avaliados ate aqui (README antigo: Donchian x ATR x R:R x EMA, mais
# ideias descartadas). Estimativa, nao contagem exata; o DSR e mostrado para varios valores.
N_TRIALS = (1, 20, 100)

SERIES = {
    "win_prev": ("win_prev_5min.csv", "WIN contrato anterior, 15/04-14/09"),
    "win_z26": ("win_z26_5min.csv", "WINZ26, 12/05-16/10 (inclui 15/09-16/10, posterior ao README antigo)"),
}


def num(x):
    x = float(x)
    return None if x != x or x in (float("inf"), float("-inf")) else round(x, 4)


def clean(d: dict) -> dict:
    return {k: (v if isinstance(v, int) else num(v) if isinstance(v, float) else v) for k, v in d.items()}


def evaluate(name: str, df: pd.DataFrame) -> dict:
    sig = generate_signals(add_indicators(df, **PARAMS), **SIGNAL)
    trades, m = run_backtest(sig, entry="next_open", **RUN)
    _, m_legacy = run_backtest(sig, entry="close", **RUN)
    out = {
        "bars": len(df), "days": int(df.datetime.dt.date.nunique()),
        "from": str(df.datetime.min()), "to": str(df.datetime.max()),
        "metrics": clean(m), "legacy_entry_at_signal_close": clean(m_legacy),
    }
    if trades.empty:
        return out | {"trades": trades}
    pnl = trades["pnl_brl"]
    out["bootstrap"] = clean(bootstrap_trades(pnl))
    out["dsr"] = {str(n): num(deflated_sharpe_ratio(pnl, n)) for n in N_TRIALS}
    stress = stress_costs(partial(run_backtest, sig, **{k: v for k, v in RUN.items() if k != "slippage_ticks"}),
                          factors=(1.0, 2.0, 3.0), slippage_ticks=RUN["slippage_ticks"])
    out["stress_costs"] = [clean(r) for r in stress[["custo_x", "gross_pnl_brl", "profit_factor"]].to_dict("records")]
    out["reasons"] = trades["reason"].value_counts().to_dict()
    monthly = pnl.groupby(pd.to_datetime(trades["exit_time"]).dt.to_period("M").astype(str)).sum()
    out["monthly_pnl"] = {k: round(float(v), 2) for k, v in monthly.items()}
    if name == "win_prev":
        parts = {}
        for label, part in zip(("train", "test"), train_test_split_time(sig, TRAIN_END), strict=True):
            _, pm = run_backtest(part, entry="next_open", **RUN)
            parts[label] = clean(pm)
        out["train_test"] = parts | {"split": TRAIN_END}
    return out | {"trades": trades}


def plot(results: dict, path: Path) -> None:
    fig, axes = plt.subplots(2, len(results), figsize=(6 * len(results), 7), squeeze=False)
    for col, (name, r) in enumerate(results.items()):
        t = r["trades"]
        ax = axes[0][col]
        if not t.empty:
            eq = t["equity_brl"]
            ax.plot(pd.to_datetime(t["exit_time"]), eq, color="#2563eb", lw=1.5)
            ax.fill_between(pd.to_datetime(t["exit_time"]), eq, eq.cummax(), where=eq < eq.cummax(),
                            color="#dc2626", alpha=0.15, label="drawdown")
            ax.legend()
            ax.set_title(f"{name}: PF {r['metrics']['profit_factor']}, t={r['metrics']['t_stat']}")
        ax.axhline(0, color="#999", lw=0.8, ls="--")
        ax.set_ylabel("capital acumulado (R$)")
        ax.tick_params(axis="x", rotation=30)
        mp = pd.Series(r.get("monthly_pnl", {}))
        axes[1][col].bar(mp.index, mp.values, color=["#16a34a" if v >= 0 else "#dc2626" for v in mp.values])
        axes[1][col].axhline(0, color="#666", lw=0.8)
        axes[1][col].set_ylabel("PnL mensal (R$)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    results = {}
    for name, (fname, desc) in SERIES.items():
        df = load_bars(CURATED / fname, min_bars_per_day=MIN_BARS_PER_DAY)
        results[name] = evaluate(name, df) | {"description": desc}
        results[name]["trades"].to_csv(REPORTS / f"trades_{name}.csv", index=False)

    summary = {k: {kk: vv for kk, vv in v.items() if kk != "trades"} for k, v in results.items()}
    summary["config"] = {"params": PARAMS, "signal": SIGNAL, "run": {k: str(v) for k, v in RUN.items()},
                         "min_bars_per_day": MIN_BARS_PER_DAY, "n_trials_assumed": list(N_TRIALS)}
    (REPORTS / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    plot(results, REPORTS / "tearsheet.png")

    for name, r in summary.items():
        if name == "config":
            continue
        m = r["metrics"]
        print(f"\n== {name}: {r['description']} ==")
        print(f"{r['days']} dias, {r['bars']} barras | trades={m.get('n_trades')} PF={m.get('profit_factor')} "
              f"PnL=R$ {m.get('gross_pnl_brl')} DD=R$ {m.get('max_drawdown_brl')} t={m.get('t_stat')}")
        leg = r["legacy_entry_at_signal_close"]
        print(f"  entrada no fechamento do sinal (legado, otimista): PF={leg.get('profit_factor')} "
              f"PnL=R$ {leg.get('gross_pnl_brl')}")
        if "bootstrap" in r:
            b = r["bootstrap"]
            print(f"  bootstrap: P(prejuizo)={b['prob_loss']} PnL p5/p50/p95="
                  f"{b['pnl_p5']}/{b['pnl_p50']}/{b['pnl_p95']}")
            print("  DSR (prob. de edge real) por n_trials:", r["dsr"])
            print("  custos x2/x3 -> PF:", [(s["custo_x"], s["profit_factor"]) for s in r["stress_costs"][1:]])
        if "train_test" in r:
            tt = r["train_test"]
            print(f"  treino PF={tt['train'].get('profit_factor')} n={tt['train'].get('n_trades')} | "
                  f"teste PF={tt['test'].get('profit_factor')} n={tt['test'].get('n_trades')}")
        print("  PnL mensal:", r.get("monthly_pnl"))


if __name__ == "__main__":
    main()
