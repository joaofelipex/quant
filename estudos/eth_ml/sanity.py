"""Testes de sanidade do AUC ~0,55 do eth_ml (rodar depois de run_study.py).

    python estudos/eth_ml/sanity.py

1. Viés de alta: acurácia do modelo vs "sempre sobe" e fração de rótulos positivos OOS.
2. Rótulos embaralhados no treino: o AUC tem de cair para ~0,5 (se não cair, há vazamento no teste).
3. Features atrasadas em k barras: sinal de microestrutura decai rápido com o atraso; sinal de regime não decai.
4. Score ingênuo sem modelo (r24, r72, taker_ratio) como AUC de referência.
5. AUC por ano.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_study import FEATURES, TEST, TRAIN, H, load, new_model  # noqa: E402

from quant.validation import walk_forward_splits  # noqa: E402


def oos_probs(df: pd.DataFrame, model: str, lag: int = 0, shuffle: bool = False, seed: int = 0) -> pd.Series:
    d = df.copy()
    if lag:
        d[FEATURES] = d[FEATURES].shift(lag)
    rng = np.random.default_rng(seed)
    purge = pd.Timedelta(hours=int(H + 1))
    out = []
    for tr, te in walk_forward_splits(d, TRAIN, TEST):
        tr = tr[tr["datetime"] < te["datetime"].min() - purge].dropna(subset=[*FEATURES, "fwd"])
        te = te.dropna(subset=FEATURES)
        y = (tr["fwd"] > 0).astype(int).to_numpy()
        if shuffle:
            y = rng.permutation(y)
        m = new_model(model).fit(tr[FEATURES], y)
        out.append(pd.Series(m.predict_proba(te[FEATURES])[:, 1], index=te.index))
    return pd.concat(out)


def auc_on(df: pd.DataFrame, score: pd.Series) -> float:
    y = df.loc[score.index, "fwd"]
    ok = y.notna() & score.notna()
    return float(roc_auc_score((y[ok] > 0).astype(int), score[ok]))


def main() -> None:
    df = load()
    base = {m: oos_probs(df, m) for m in ("logit", "gbm")}
    idx = base["logit"].index
    y = (df.loc[idx, "fwd"].dropna() > 0).astype(int)
    up = y.mean()
    print(f"OOS: {len(idx)} barras | rotulos positivos: {up:.3f} (always-up acerta {max(up, 1 - up):.3f})")

    print("\n[1] AUC e acuracia do modelo (limiar 0,5)")
    for m, p in base.items():
        pred = (p.loc[y.index] > 0.5).astype(int)
        acc = (pred == y).mean()
        print(f"  {m:6s} AUC {auc_on(df, p):.4f}  acuracia {acc:.3f}  prev. alta em {pred.mean():.1%} das barras")

    print("\n[2] Rotulos embaralhados no treino (esperado ~0,50)")
    for m in base:
        print(f"  {m:6s} AUC {auc_on(df, oos_probs(df, m, shuffle=True)):.4f}")

    print("\n[3] Features atrasadas em k barras extras")
    for m in base:
        row = {k: auc_on(df, base[m] if k == 0 else oos_probs(df, m, lag=k)) for k in (0, 1, 2, 6, 24)}
        print("  " + m.ljust(6) + "  ".join(f"lag{k}: {a:.4f}" for k, a in row.items()))

    print("\n[4] Score ingenuo, sem modelo (AUC contra o mesmo rotulo)")
    for f in ("r1", "r4", "r24", "r72", "taker_ratio", "dist_ema24", "vol_ratio"):
        print(f"  {f:12s} {auc_on(df, df.loc[idx, f]):.4f}")

    print("\n[5] AUC por ano")
    for m in base:
        yr = {}
        for year, g in df.loc[idx].groupby(df.loc[idx, "datetime"].dt.year):
            yr[year] = auc_on(df, base[m].loc[g.index])
        print("  " + m.ljust(6) + "  ".join(f"{k}: {a:.4f}" for k, a in yr.items()))


if __name__ == "__main__":
    main()
