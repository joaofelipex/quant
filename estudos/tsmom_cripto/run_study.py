"""Estudo tsmom_cripto: tendencia diaria multi-ativo (ver README para o desenho pre-registrado).

    for s in BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT; do
        python -m quant.data.fetch_binance $s 1d 2020-01 2025-10
        python -m quant.data.fetch_funding $s 2020-01 2025-10
    done
    python estudos/tsmom_cripto/run_study.py

Nada aqui e ajustado: os parametros do README sao fixos. O hold-out (2023-07 em diante) so entra no veredito final.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from quant.metrics import sharpe  # noqa: E402
from quant.strategies import tsmom  # noqa: E402
from quant.validation import deflated_sharpe_ratio  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "dados" / "raw" / "binance"
REPORTS = Path(__file__).resolve().parent / "reports"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
DEV_START, HOLDOUT_START = "2020-09-01", "2023-07-01"
COST_BPS = 7.0
PPY = 365
N_TRIALS = 30
LOOKBACK_SETS = {"rapido": (10, 30, 60), "base": (20, 60, 120), "lento": (60, 120, 250)}
PRIMARY = ("base", False)  # (conjunto de janelas, long_only)


def load_panel(symbols):
    opens, closes, funds = {}, {}, {}
    for s in symbols:
        d = pd.read_csv(RAW / f"{s}_1d.csv", parse_dates=["datetime"])
        d["datetime"] = d["datetime"].dt.tz_localize(None).dt.normalize()
        d = d.set_index("datetime")
        opens[s], closes[s] = d["open"], d["close"]
        f = pd.read_csv(RAW / f"{s}_funding.csv", parse_dates=["datetime"])
        f["day"] = f["datetime"].dt.tz_localize(None).dt.normalize()
        funds[s] = f.groupby("day")["funding_rate"].sum()
    return pd.DataFrame(opens), pd.DataFrame(closes), pd.DataFrame(funds).reindex(pd.DataFrame(closes).index)


def run_variant(open_, close, fund, lookbacks, long_only, cost_bps=COST_BPS):
    w = tsmom.apply_band(tsmom.target_weights(close, lookbacks=lookbacks, long_only=long_only))
    return tsmom.portfolio_returns(open_, w, fund, cost_bps=cost_bps), w


def basket_returns(open_):
    ret = open_.shift(-2) / open_.shift(-1) - 1
    return ret.mean(axis=1, skipna=True).dropna()  # cesta equiponderada, rebalanceada todo dia, sem custo (benchmark)


def stats(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    ann = float(r.mean() * PPY)
    return {"ret_anual": ann, "vol": float(r.std() * np.sqrt(PPY)), "sharpe": sharpe(r, PPY), "max_dd": dd,
            "calmar": ann / abs(dd) if dd < 0 else float("nan")}


def hac_alpha_beta(y: pd.Series, x: pd.Series, lags: int = 10):
    """OLS y = a + b x com erro-padrao Newey-West. Devolve (alfa anual, beta, t do alfa, t do beta)."""
    d = pd.concat([y, x], axis=1).dropna()
    Y, X = d.iloc[:, 0].to_numpy(), np.column_stack([np.ones(len(d)), d.iloc[:, 1].to_numpy()])
    b = np.linalg.solve(X.T @ X, X.T @ Y)
    e = Y - X @ b
    xe = X * e[:, None]
    S = xe.T @ xe
    for k in range(1, lags + 1):
        G = xe[k:].T @ xe[:-k]
        S += (1 - k / (lags + 1)) * (G + G.T)
    inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(inv @ S @ inv))
    return float(b[0] * PPY), float(b[1]), float(b[0] / se[0]), float(b[1] / se[1])


def block_bootstrap_sharpe(r: pd.Series, block: int = 20, n: int = 5000, seed: int = 0):
    rng = np.random.default_rng(seed)
    x = r.to_numpy()
    m = len(x)
    n_blocks = int(np.ceil(m / block))
    starts = rng.integers(0, m, size=(n, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % m
    sims = x[idx.reshape(n, -1)[:, :m]]
    sr = sims.mean(axis=1) / sims.std(axis=1, ddof=1) * np.sqrt(PPY)
    return float(np.percentile(sr, 5)), float(np.percentile(sr, 95)), float((sr <= 0).mean())


def fmt(df: pd.DataFrame, nd=3) -> str:
    return "```\n" + df.round(nd).to_string() + "\n```"


def main() -> None:
    open_, close, fund = load_panel(SYMBOLS)
    sl = lambda s, a, b=None: s[(s.index >= a) & ((s.index < b) if b else True)]  # noqa: E731
    bench = basket_returns(open_)
    btc = (open_["BTCUSDT"].shift(-2) / open_["BTCUSDT"].shift(-1) - 1).dropna()

    # ---- 1. todas as variantes (robustez, nao selecao) -------------------------------------------------------
    rows, results = [], {}
    for lname, lbs in LOOKBACK_SETS.items():
        for lo in (False, True):
            res, _ = run_variant(open_, close, fund, lbs, lo)
            net = sl(res["net"], DEV_START)
            key = (lname, lo)
            results[key] = res
            rows.append({"variante": f"{lname}_{'long_only' if lo else 'long_short'}",
                         "sharpe_dev": sharpe(sl(net, DEV_START, HOLDOUT_START), PPY),
                         "sharpe_holdout": sharpe(sl(net, HOLDOUT_START), PPY),
                         "sharpe_total": sharpe(net, PPY), "giro_ano": res["turnover"].sum() / (len(res) / PPY)})
    variants = pd.DataFrame(rows).set_index("variante")

    # ---- 2. variante primaria ----------------------------------------------------------------------------------
    res = results[PRIMARY]
    periods = {"dev": (DEV_START, HOLDOUT_START), "holdout": (HOLDOUT_START, None), "total": (DEV_START, None)}
    perf = {}
    for pname, (a, b) in periods.items():
        r = sl(res["net"], a, b)
        perf[pname] = {**stats(r), "funding_ano": float(sl(res["funding"], a, b).mean() * PPY),
                       "custo_ano": float(sl(res["cost"], a, b).mean() * PPY),
                       "giro_ano": float(sl(res["turnover"], a, b).sum() / (len(r) / PPY))}
    for pname, (a, b) in periods.items():
        perf[f"cesta_{pname}"] = stats(sl(bench, a, b))
        perf[f"btc_{pname}"] = stats(sl(btc, a, b))
    perf_df = pd.DataFrame(perf).T

    ho = sl(res["net"], HOLDOUT_START)
    alpha, beta, t_alpha, t_beta = hac_alpha_beta(ho, sl(bench, HOLDOUT_START))
    a_all, b_all, t_all, _ = hac_alpha_beta(sl(res["net"], DEV_START), sl(bench, DEV_START))
    dsr = deflated_sharpe_ratio(ho, N_TRIALS)
    lo5, hi95, p_le0 = block_bootstrap_sharpe(ho)

    stress = pd.DataFrame({
        f"custo_x{f:g}": {
            "sharpe_holdout": sharpe(sl(run_variant(open_, close, fund, LOOKBACK_SETS["base"], False,
                                                    COST_BPS * f)[0]["net"], HOLDOUT_START), PPY),
            "sharpe_total": sharpe(sl(run_variant(open_, close, fund, LOOKBACK_SETS["base"], False,
                                                  COST_BPS * f)[0]["net"], DEV_START), PPY)}
        for f in (0, 1, 2, 4)}).T

    loo = {}
    for s in SYMBOLS:
        keep = [x for x in SYMBOLS if x != s]
        r2, _ = run_variant(open_[keep], close[keep], fund[keep], LOOKBACK_SETS["base"], False)
        loo[f"sem_{s[:-4]}"] = {"sharpe_holdout": sharpe(sl(r2["net"], HOLDOUT_START), PPY),
                                "sharpe_total": sharpe(sl(r2["net"], DEV_START), PPY)}
    loo = pd.DataFrame(loo).T

    yearly = pd.DataFrame({
        "estrategia_ret": res["net"].groupby(res.index.year).sum(),
        "estrategia_sharpe": res["net"].groupby(res.index.year).apply(lambda r: sharpe(r, PPY)),
        "cesta_ret": bench.groupby(bench.index.year).sum()}).dropna()

    # ---- 3. veredito segundo os criterios pre-registrados -----------------------------------------------------
    checks = {
        "1. Sharpe liquido > 0 e alfa t > 2 (hold-out)": perf["holdout"]["sharpe"] > 0 and t_alpha > 2,
        f"2. DSR >= 0,95 (N_TRIALS={N_TRIALS})": dsr >= 0.95,
        "3. Sharpe > 0 com custos x2 (hold-out)": stress.loc["custo_x2", "sharpe_holdout"] > 0,
        "4. Bootstrap: P(Sharpe <= 0) < 5%": p_le0 < 0.05,
        "5. Positivo sem qualquer ativo (hold-out) e em todos os anos":
            bool((loo["sharpe_holdout"] > 0).all() and (yearly["estrategia_ret"] > 0).all()),
    }
    verdict = "APROVADA" if all(checks.values()) else "REPROVADA"

    # ---- 4. pesos de hoje e relatorio -------------------------------------------------------------------------
    _, w = run_variant(open_, close, fund, LOOKBACK_SETS["base"], False)
    today = w.iloc[-1].rename("peso").to_frame()
    REPORTS.mkdir(exist_ok=True)
    today.to_csv(REPORTS / "pesos_atuais.csv")

    out = f"""# tsmom_cripto - resultados

Periodo: {open_.index.min():%Y-%m-%d} a {open_.index.max():%Y-%m-%d}.
Dev {DEV_START} a {HOLDOUT_START}; hold-out depois.
Variante primaria: {PRIMARY[0]} / {'long_only' if PRIMARY[1] else 'long_short'}. Custo {COST_BPS:g} bps + funding real.

## Veredito: **{verdict}**
""" + "\n".join(f"- [{'x' if v else ' '}] {k}" for k, v in checks.items()) + f"""

## Desempenho da variante primaria (liquido de custos e funding)
{fmt(perf_df)}

Hold-out vs cesta equiponderada: beta {beta:.2f} (t {t_beta:.1f}), **alfa {alpha:.1%} a.a. (t {t_alpha:.2f})**.
Periodo total: beta {b_all:.2f}, alfa {a_all:.1%} a.a. (t {t_all:.2f}).
DSR (hold-out, N_TRIALS={N_TRIALS}): {dsr:.3f}.
Bootstrap em blocos do Sharpe (hold-out): IC 90% [{lo5:.2f}, {hi95:.2f}], P(Sharpe <= 0) = {p_le0:.1%}.

## Todas as variantes (robustez; Sharpe liquido)
{fmt(variants)}

## Estresse de custos (variante primaria)
{fmt(stress)}

## Sem cada ativo (variante primaria)
{fmt(loo)}

## Por ano (variante primaria vs cesta; retorno somado dos dias)
{fmt(yearly)}

## Pesos alvo no ultimo dia ({open_.index.max():%Y-%m-%d})
{fmt(today)}
"""
    (REPORTS / "resultados.md").write_text(out, encoding="utf-8")
    print(out)

    fig, ax = plt.subplots(figsize=(10, 5))
    cut = pd.Timestamp(DEV_START)
    for name, r in (("estrategia (primaria)", res["net"]), ("cesta equiponderada", bench), ("BTC", btc)):
        r = r[r.index >= cut]
        ax.plot(r.index, (1 + r).cumprod(), label=name)
    ax.axvline(pd.Timestamp(HOLDOUT_START), color="k", ls="--", lw=0.8, label="inicio do hold-out")
    ax.set_yscale("log")
    ax.set_title("tsmom_cripto - equity liquida")
    ax.legend()
    fig.savefig(REPORTS / "equity.png", dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()
