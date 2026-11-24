"""Estudo xsmom_cripto: momentum de corte transversal neutro em dolar (ver README: desenho pre-registrado e fixo).

    python estudos/xsmom_cripto/run_study.py      # usa os dados baixados para a tsmom_cripto

Nada aqui e ajustado depois de olhar o resultado. O hold-out (2023-07 em diante) entra uma unica vez, no veredito.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tsmom_cripto"))
import run_study as base  # noqa: E402

from quant.metrics import sharpe  # noqa: E402
from quant.strategies import tsmom  # noqa: E402
from quant.validation import deflated_sharpe_ratio  # noqa: E402

REPORTS = Path(__file__).resolve().parent / "reports"
PRIMARY_LB, ROBUST_LBS = 60, (30, 90)
N_TRIALS = 33
REB_DAYS, N_SIDE, LEG = 7, 2, 0.5
PPY = base.PPY


def weights(close: pd.DataFrame, lookback: int) -> pd.DataFrame:
    ret = close / close.shift(lookback) - 1
    vol = tsmom.realized_vol(close, 30)
    out = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    cur = pd.Series(0.0, index=close.columns)
    first = close.index[0]
    for i, day in enumerate(close.index):
        if (day - first).days % REB_DAYS == 0:  # rebalanceia a cada 7 dias contados do primeiro dia
            r, v = ret.loc[day].dropna(), vol.loc[day]
            r = r[v.reindex(r.index).notna()]
            cur = pd.Series(0.0, index=close.columns)
            if len(r) >= 2 * N_SIDE:
                order = r.sort_values()
                for names, sign in ((order.index[-N_SIDE:], 1.0), (order.index[:N_SIDE], -1.0)):
                    inv = 1.0 / v[names]
                    cur[names] = sign * LEG * inv / inv.sum()
        out.iloc[i] = cur
    return out


def run(lookback, open_, close, fund, cost_bps=base.COST_BPS):
    return tsmom.portfolio_returns(open_, weights(close, lookback), fund, cost_bps=cost_bps)


def main() -> None:
    open_, close, fund = base.load_panel(base.SYMBOLS)
    sl = lambda s, a, b=None: s[(s.index >= a) & ((s.index < b) if b else True)]  # noqa: E731
    bench = base.basket_returns(open_)
    D, H = base.DEV_START, base.HOLDOUT_START
    res = {lb: run(lb, open_, close, fund) for lb in (PRIMARY_LB, *ROBUST_LBS)}
    prim = res[PRIMARY_LB]
    ho = sl(prim["net"], H)

    perf = pd.DataFrame({p: base.stats(sl(prim["net"], a, b)) for p, (a, b) in
                         {"dev": (D, H), "holdout": (H, None), "total": (D, None)}.items()}).T
    alpha, beta, t_alpha, _ = base.hac_alpha_beta(ho, sl(bench, H))
    dsr = deflated_sharpe_ratio(ho, N_TRIALS)
    lo5, hi95, p_le0 = base.block_bootstrap_sharpe(ho)
    x2 = sl(run(PRIMARY_LB, open_, close, fund, cost_bps=2 * base.COST_BPS)["net"], H)
    rob = pd.DataFrame({f"lb{lb}": {"sharpe_dev": sharpe(sl(r["net"], D, H), PPY),
                                    "sharpe_holdout": sharpe(sl(r["net"], H), PPY)}
                        for lb, r in res.items()}).T
    loo = {}
    for s in base.SYMBOLS:
        keep = [c for c in base.SYMBOLS if c != s]
        loo[f"sem_{s}"] = sharpe(sl(run(PRIMARY_LB, open_[keep], close[keep], fund[keep])["net"], H), PPY)
    yearly = prim["net"].groupby(prim["net"].index.year).sum()

    ok = [alpha > 0 and ho.mean() > 0 and t_alpha > 2, dsr >= 0.95, sharpe(x2, PPY) > 0, p_le0 < 0.05,
          all(v > 0 for v in loo.values()) and bool((yearly[yearly.index >= 2023] > 0).all())]
    verdict = "APROVADA" if all(ok) else "REPROVADA"
    lines = [f"# xsmom_cripto - resultados\n\n## Veredito: **{verdict}**"]
    names = ["1. Sharpe liquido > 0 e alfa t > 2", "2. DSR >= 0,95 (N_TRIALS=33)", "3. Sharpe > 0 com custos x2",
             "4. Bootstrap: P(Sharpe <= 0) < 5%", "5. Positivo sem cada ativo e em todos os anos (2023+)"]
    lines += [f"- [{'x' if o else ' '}] {n}" for o, n in zip(ok, names, strict=True)]
    lines += ["\n## Desempenho da variante primaria (lb60, liquido)", base.fmt(perf),
              f"\nHold-out vs cesta: beta {beta:.2f}, alfa {alpha:.1%} a.a. (t {t_alpha:.2f}). DSR {dsr:.3f}.",
              f"Bootstrap em blocos (hold-out): IC 90% [{lo5:.2f}, {hi95:.2f}], P(Sharpe <= 0) = {p_le0:.1%}.",
              f"Sharpe hold-out com custos x2: {sharpe(x2, PPY):.2f}.", "\n## Robustez (janelas)", base.fmt(rob),
              "\n## Sem cada ativo (Sharpe hold-out)", base.fmt(pd.Series(loo).to_frame("sharpe_holdout")),
              "\n## Retorno somado por ano", base.fmt(yearly.to_frame("estrategia_ret"))]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "resultados.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
