"""Da para prever para onde vai a proxima vela de 30 min? BTC e ETH, 2023 a set/2026, tudo que as velas dao.

    python estudos/vela_30min/testar.py

Features so do passado (retornos, formato da vela, volatilidade, volume, numero de negocios, fracao de agressao
compradora, hora, o outro ativo). Treina em 2023-24, escolhe o limiar em 2025, prova em 2026 (olhado uma vez).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PRECOS = Path(__file__).resolve().parents[2] / "dados" / "raw" / "binance"
LIMIARES = (0.0, 0.02, 0.05, 0.08)
CUSTOS = {"sem custo": 0.0, "4 bps": 4.0, "30 bps": 30.0}  # ida e volta


def velas(sym: str) -> pd.DataFrame:
    d = pd.read_csv(PRECOS / f"{sym}_1m.csv", parse_dates=["datetime"]).set_index("datetime")
    agg = d.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
                                   "trades": "sum", "taker_buy_base": "sum"})
    n = d["close"].resample("30min").count()
    return agg[n >= 25]  # velas com buraco ficam de fora


def features(d: pd.DataFrame, prefixo: str) -> pd.DataFrame:
    c, r = d["close"], d["close"].pct_change()
    faixa = (d["high"] - d["low"]).replace(0, np.nan)
    f = {f"ret{k}": c.pct_change(k) for k in (1, 2, 4, 8, 16, 48, 336)}
    f["vol16"], f["vol_rel"] = r.rolling(16).std(), r.rolling(16).std() / r.rolling(336).std()
    f["corpo"] = (c - d["open"]) / faixa
    f["pavio_cima"] = (d["high"] - d[["open", "close"]].max(axis=1)) / faixa
    f["posicao"] = (c - d["low"]) / faixa
    f["dist_max48"] = c / d["high"].rolling(48).max() - 1
    f["dist_min48"] = c / d["low"].rolling(48).min() - 1
    for col in ("volume", "trades"):
        lv = np.log1p(d[col])
        f[f"{col}_z"] = (lv - lv.rolling(336).mean()) / lv.rolling(336).std()
    for k in (1, 4, 16):  # leitura de fluxo: fracao do volume que agrediu na compra
        f[f"agressao{k}"] = d["taker_buy_base"].rolling(k).sum() / d["volume"].rolling(k).sum().replace(0, np.nan)
    return pd.DataFrame(f).add_prefix(prefixo)


def liquido(p: np.ndarray, ret: np.ndarray, limiar: float, custo: float) -> tuple[int, float, float]:
    """(operacoes, bps liquidos medios por operacao, total em %). Manter o mesmo lado nao paga custo de novo."""
    pos = np.where(p > 0.5 + limiar, 1, np.where(p < 0.5 - limiar, -1, 0))
    anterior = np.concatenate([[0], pos[:-1]])
    giro = np.abs(pos - anterior) / 2  # 1 = uma ida e volta completa (virar de lado)
    pnl = pos * ret - giro * custo
    ops = int(((pos != 0) & (pos != anterior)).sum())
    return ops, float(pnl.sum() / ops) if ops else 0.0, float(pnl.sum() / 100)


def main() -> None:
    base = {s: velas(s) for s in ("BTCUSDT", "ETHUSDT")}
    for sym, outro in (("BTCUSDT", "ETHUSDT"), ("ETHUSDT", "BTCUSDT")):
        d = base[sym]
        x = features(d, "").join(features(base[outro], "outro_"))
        hora = x.index.hour + x.index.minute / 60
        x["h_sin"], x["h_cos"] = np.sin(2 * np.pi * hora / 24), np.cos(2 * np.pi * hora / 24)
        seguinte = d["close"].shift(-1) / d["close"] - 1
        continua = d.index.to_series().shift(-1) - d.index.to_series() == pd.Timedelta("30min")
        ok = x.notna().all(axis=1) & continua & seguinte.notna()
        x, ret = x[ok], (seguinte[ok] * 1e4).to_numpy()
        y = (ret > 0).astype(int)
        ano = x.index.year
        tr, va, te = ano <= 2024, ano == 2025, ano == 2026
        # a ultima linha de cada bloco tem alvo na primeira barra do seguinte: sai (purga)
        tr[np.flatnonzero(tr)[-1]] = False
        va[np.flatnonzero(va)[-1]] = False
        print(f"\n=== {sym} | treino {tr.sum()} velas, escolha {va.sum()}, prova {te.sum()} | "
              f"movimento medio de 30 min na prova: {np.abs(ret[te]).mean():.1f} bps")
        modelos = {
            "logistica": make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)),
            "arvores": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.02, max_iter=250,
                                                      min_samples_leaf=500, random_state=0),
        }
        probas = {}
        for nome, m in modelos.items():
            m.fit(x[tr], y[tr])
            probas[nome] = m.predict_proba(x)[:, 1]
        ultima = np.sign(x["ret1"].to_numpy())
        probas["seguir a ultima vela"] = 0.5 + 0.1 * ultima
        probas["contra a ultima vela"] = 0.5 - 0.1 * ultima
        for nome, p in probas.items():
            acerto = ((p[te] > 0.5) == (y[te] == 1)).mean()
            print(f"{nome}: AUC prova {roc_auc_score(y[te], p[te]):.3f} | acerto {acerto:.1%}")
            for rotulo, custo in CUSTOS.items():
                limiar = max(LIMIARES, key=lambda lim: liquido(p[va], ret[va], lim, custo)[2])
                v, t = liquido(p[va], ret[va], limiar, custo), liquido(p[te], ret[te], limiar, custo)
                print(f"   {rotulo:>9}: limiar {limiar:.2f} | 2025 {v[0]:>5} ops {v[1]:>7.1f} bps/op {v[2]:>8.1f}% "
                      f"| 2026 {t[0]:>5} ops {t[1]:>7.1f} bps/op {t[2]:>8.1f}%")


if __name__ == "__main__":
    main()
