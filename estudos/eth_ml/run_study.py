"""Estudo eth_ml: ML (logit e gradient boosting) preve a direcao do ETH em barras de 1 h? Walk-forward puro, com custos.

    python -m quant.data.fetch_binance ETHUSDT 1h 2021-01 2025-10
    python estudos/eth_ml/run_study.py

Desenho (fixado ANTES de olhar resultado; nada foi reotimizado):
* features causais (``quant.ml.features``); rotulo = retorno de abertura(t+1) a abertura(t+1+H) > 0, H = 4.
* walk-forward: treina em 540 dias, testa nos 30 seguintes, desliza 30; purga das linhas de treino cujo rotulo
  invade o teste. So a serie OOS concatenada e avaliada.
* posicao = sinal do modelo se |p - 0,5| > limiar, senao zero; reavaliada a cada barra; custo sobre a rotatividade.
* N_TRIALS = 2 modelos x 3 limiares + 1 baseline de momentum = 7 variantes olhadas (usadas no DSR).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from quant.metrics import sharpe  # noqa: E402
from quant.ml.features import FEATURES, forward_return, make_features  # noqa: E402
from quant.validation import deflated_sharpe_ratio, walk_forward_splits  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "dados" / "raw" / "binance"
REPORTS = Path(__file__).resolve().parent / "reports"

H = 4
TRAIN, TEST = "540D", "30D"
THRESHOLDS = (0.0, 0.02, 0.05)
FEE_BPS, SLIP_BPS = 5.0, 2.0  # por lado, sobre o nocional negociado
PPY = 24 * 365
N_TRIALS = 7


def new_model(name: str):
    if name == "logit":
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
    return HistGradientBoostingClassifier(
        max_depth=3, max_iter=150, learning_rate=0.05, min_samples_leaf=200, random_state=0
    )


def load(symbol: str = "ETHUSDT") -> pd.DataFrame:
    df = pd.read_csv(RAW / f"{symbol}_1h.csv", parse_dates=["datetime"])
    df["datetime"] = df["datetime"].dt.tz_localize(None)
    df = df.sort_values("datetime").reset_index(drop=True)
    feats = make_features(df)
    df = pd.concat([df, feats], axis=1)
    df["fwd"] = forward_return(df, H)
    df["ret1"] = df["open"].shift(-2) / df["open"].shift(-1) - 1  # retorno da barra em que a posicao fica exposta
    return df


def walk_forward_probs(df: pd.DataFrame) -> dict[str, pd.Series]:
    probs = {m: [] for m in ("logit", "gbm")}
    purge = pd.Timedelta(hours=int(H + 1))
    for tr, te in walk_forward_splits(df, TRAIN, TEST):
        tr = tr[tr["datetime"] < te["datetime"].min() - purge].dropna(subset=[*FEATURES, "fwd"])
        te = te.dropna(subset=FEATURES)
        y = (tr["fwd"] > 0).astype(int)
        for name in probs:
            model = new_model(name).fit(tr[FEATURES], y)
            probs[name].append(pd.Series(model.predict_proba(te[FEATURES])[:, 1], index=te.index))
    return {k: pd.concat(v) for k, v in probs.items()}


def net_returns(pos: pd.Series, ret1: pd.Series, cost_x: float = 1.0) -> pd.Series:
    turnover = pos.diff().abs().fillna(pos.abs())
    return pos * ret1 - turnover * (FEE_BPS + SLIP_BPS) * cost_x / 1e4


def stats(net: pd.Series, pos: pd.Series) -> dict:
    eq = (1 + net).cumprod()
    years = len(net) / PPY
    return {
        "ret_anual": float(net.mean() * PPY),
        "sharpe": sharpe(net, PPY),
        "max_dd": float((eq / eq.cummax() - 1).min()),
        "giro_ano": float(pos.diff().abs().sum() / years),
        "tempo_posicionado": float((pos != 0).mean()),
    }


def main() -> None:
    df = load()
    probs = walk_forward_probs(df)
    oos = probs["logit"].index.intersection(df.index[df["ret1"].notna()])
    d = df.loc[oos]
    print(f"OOS: {d['datetime'].min()} a {d['datetime'].max()} ({len(d)} barras, {len(d) / PPY:.2f} anos)")

    variants: dict[str, pd.Series] = {"buy_and_hold": pd.Series(1.0, index=oos)}
    variants["momentum_r24"] = np.sign(d["r24"]).fillna(0.0)
    auc = {}
    for m, p in probs.items():
        p = p.loc[oos]
        auc[m] = roc_auc_score((d["fwd"] > 0).astype(int)[d["fwd"].notna()], p[d["fwd"].notna()])
        for t in THRESHOLDS:
            side = np.where(p > 0.5 + t, 1.0, np.where(p < 0.5 - t, -1.0, 0.0))
            variants[f"{m}_thr{t:.2f}"] = pd.Series(side, index=oos)

    rows, nets = [], {}
    for name, pos in variants.items():
        net = net_returns(pos, d["ret1"])
        nets[name] = net
        s = stats(net, pos)
        s["sharpe_bruto"] = sharpe(pos * d["ret1"], PPY)
        s["sharpe_x2"] = sharpe(net_returns(pos, d["ret1"], 2.0), PPY)
        s["sharpe_x3"] = sharpe(net_returns(pos, d["ret1"], 3.0), PPY)
        s["dsr"] = float("nan") if name == "buy_and_hold" else deflated_sharpe_ratio(net, N_TRIALS)
        rows.append({"variante": name, **s})
    table = pd.DataFrame(rows).set_index("variante")

    candidates = table.drop(index="buy_and_hold")
    best = candidates["sharpe"].idxmax()
    by_year = nets[best].groupby(d["datetime"].dt.year).apply(lambda r: sharpe(r, PPY))

    REPORTS.mkdir(exist_ok=True)
    fmt = "```\n" + table.round(3).to_string() + "\n```"
    out = (
        f"# eth_ml - resultados OOS\n\nOOS: {d['datetime'].min():%Y-%m-%d} a {d['datetime'].max():%Y-%m-%d} "
        f"({len(d)} barras). AUC OOS: logit {auc['logit']:.4f}, gbm {auc['gbm']:.4f} (0,5 = sem informacao).\n"
        f"Custo: {FEE_BPS:.0f} bps taxa + {SLIP_BPS:.0f} bps slippage por lado. DSR com N_TRIALS={N_TRIALS} "
        f"(por barra; as barras tem retornos sobrepostos pelo horizonte, entao e otimista).\n\n{fmt}\n\n"
        f"Melhor por Sharpe liquido: **{best}**. Sharpe por ano:\n\n```\n{by_year.round(2).to_string()}\n```\n"
    )
    (REPORTS / "resultados.md").write_text(out, encoding="utf-8")
    print(out)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name in ("buy_and_hold", "momentum_r24", best):
        ax.plot(d["datetime"], (1 + nets[name]).cumprod(), label=name)
    ax.set_yscale("log")
    ax.set_title("eth_ml - equity OOS liquida de custos")
    ax.legend()
    fig.savefig(REPORTS / "equity.png", dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()
