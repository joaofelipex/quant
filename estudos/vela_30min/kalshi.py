"""A leitura de 30 min em metais, indices e cambio, onde a taxa e baixa. Velas publicas da Kalshi DEMO (sem chave).

    python estudos/vela_30min/kalshi.py --baixar   # velas de 1 min -> 30 min em dados/raw/kalshi_demo/
    python estudos/vela_30min/kalshi.py            # teste

Compra executa no ask e venda no bid do fechamento da vela (o spread entra no resultado), mais a taxa da classe por
lado. Por classe, um modelo unico para todos os ativos: treino nos primeiros 50% do tempo, limiar nos 25% seguintes,
prova nos 25% finais.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
from quant.agent import FEE_BPS  # noqa: E402
from quant.live import assets  # noqa: E402

PASTA = RAIZ / "dados" / "raw" / "kalshi_demo"
HOST = "https://external-api.demo.kalshi.co/trade-api/v2/margin/markets"
CLASSES = ("Metals", "Indices", "FX")
LIMIARES = (0.0, 0.02, 0.05, 0.08, 0.12)
SPREAD_MAX = 50.0  # bps; acima disso a cotacao da demo nao serve para executar


def pedir(sessao: requests.Session, url: str) -> list[dict]:
    for tentativa in range(6):
        try:
            r = sessao.get(url, timeout=30)
        except requests.RequestException:
            if tentativa == 5:
                raise
            time.sleep(2**tentativa)
            continue
        if r.status_code == 200:
            return r.json().get("candlesticks", [])
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
        time.sleep(2**tentativa)
    r.raise_for_status()
    return []


def baixar() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    fim = int(time.time()) // 1800 * 1800
    for nome, info in assets.CATALOG.items():
        destino = PASTA / f"{nome}_30m.csv"
        if info["cls"] not in CLASSES or destino.exists():
            continue
        url = f"{HOST}/{info['ticker']}/candlesticks?period_interval="
        # acha o comeco do historico com velas de 1 h, para nao varrer meses vazios de 1 em 1 min
        inicio, ate = fim, fim
        while True:
            c = pedir(s, f"{url}60&start_ts={ate - 300 * 3600}&end_ts={ate}")
            if not c:
                break
            inicio, ate = min(x["end_period_ts"] for x in c) - 3600, ate - 300 * 3600
            time.sleep(0.1)
        linhas = {}
        for ini in range(inicio // 1800 * 1800, fim, 300 * 60):
            for c in pedir(s, f"{url}1&start_ts={ini}&end_ts={min(ini + 300 * 60, fim)}"):
                try:
                    b, a = float(c["bid"]["close"]), float(c["ask"]["close"])
                except (KeyError, TypeError, ValueError):
                    continue
                linhas[int(c["end_period_ts"])] = (b, a, float(c.get("volume") or 0))
            time.sleep(0.1)
        d = pd.DataFrame.from_dict(linhas, orient="index", columns=["bid", "ask", "volume"]).sort_index()
        d = d[(d.bid > 0) & (d.ask >= d.bid)]
        d["mid"] = (d.bid + d.ask) / 2
        d["balde"] = (d.index - 60) // 1800 * 1800
        v = d.groupby("balde").agg(open=("mid", "first"), high=("mid", "max"), low=("mid", "min"),
                                   close=("mid", "last"),
                                   bid=("bid", "last"), ask=("ask", "last"), volume=("volume", "sum"),
                                   minutos=("mid", "size"))
        v[v.minutos >= 25].to_csv(destino)
        print(f"{nome}: {len(v)} velas de 30 min desde {pd.to_datetime(inicio, unit='s').date()}", flush=True)


def preparar(nome: str) -> pd.DataFrame | None:
    arq = PASTA / f"{nome}_30m.csv"
    if not arq.exists():
        return None
    d = pd.read_csv(arq).set_index("balde")
    # pico falso da demo: fechamento a mais de 3% da mediana das 25 velas ao redor
    d = d[(d.close / d.close.rolling(25, center=True, min_periods=5).median() - 1).abs() < 0.03]
    if len(d) < 800:
        return None
    c, r = d.close, d.close.pct_change()
    faixa = (d.high - d.low).replace(0, np.nan)
    f = {f"ret{k}": c.pct_change(k) for k in (1, 2, 4, 8, 16, 48)}
    f["vol16"], f["vol_rel"] = r.rolling(16).std(), r.rolling(16).std() / r.rolling(200).std()
    f["corpo"] = ((c - d.open) / faixa).fillna(0)
    f["posicao"] = ((c - d.low) / faixa).fillna(0.5)
    f["dist_max48"], f["dist_min48"] = c / d.high.rolling(48).max() - 1, c / d.low.rolling(48).min() - 1
    f["spread"] = (d.ask - d.bid) / c * 1e4
    f["volume"] = np.log1p(d.volume)
    hora = (d.index % 86400) / 3600
    f["h_sin"], f["h_cos"] = np.sin(2 * np.pi * hora / 24), np.cos(2 * np.pi * hora / 24)
    x = pd.DataFrame(f, index=d.index)
    prox = d.shift(-1)
    x["alvo_ret"] = (prox.close / c - 1) * 1e4
    # comprar agora no ask e vender no bid da vela seguinte; vender no bid e recomprar no ask
    x["longo"] = (prox.bid / d.ask - 1) * 1e4
    x["curto"] = (d.bid / prox.ask - 1) * 1e4
    seguida = d.index.to_series().shift(-1) - d.index.to_series() == 1800
    ok = seguida & (x.spread <= SPREAD_MAX) & ((prox.ask - prox.bid) / prox.close * 1e4 <= SPREAD_MAX)
    x = x[ok].dropna()
    x["ativo"] = nome
    return x


def operar(p: np.ndarray, x: pd.DataFrame, limiar: float, taxa: float) -> np.ndarray:
    """Liquido em bps de cada operacao de uma vela (entra e sai sempre: paga spread e as duas taxas)."""
    compra, venda = p > 0.5 + limiar, p < 0.5 - limiar
    return np.concatenate([x.longo.to_numpy()[compra], x.curto.to_numpy()[venda]]) - 2 * taxa


def testar() -> None:
    for classe in CLASSES:
        partes = [p for a, i in assets.CATALOG.items() if i["cls"] == classe and (p := preparar(a)) is not None]
        if not partes:
            print(f"\n=== {classe}: sem dados suficientes")
            continue
        x = pd.concat(partes).sort_index()
        q50, q75 = np.quantile(x.index, [0.5, 0.75])
        tr, va, te = x.index < q50 - 1800, (x.index >= q50) & (x.index < q75 - 1800), x.index >= q75
        cols = [c for c in x.columns if c not in ("alvo_ret", "longo", "curto", "ativo")]
        y = (x.alvo_ret > 0).astype(int).to_numpy()
        mexeu = (x.alvo_ret != 0).to_numpy()
        datas = pd.to_datetime([x.index.min(), q50, q75, x.index.max()], unit="s").strftime("%d/%m").tolist()
        print(f"\n=== {classe}: {len(partes)} ativos, treino {tr.sum()} / escolha {va.sum()} / prova {te.sum()} velas "
              f"({' | '.join(datas)}) | movimento medio {x.alvo_ret[te].abs().mean():.1f} bps, spread mediano "
              f"{x.spread[te].median():.1f} bps, taxa {FEE_BPS[classe]} bps por lado")
        probas = {}
        for nome, m in (("logistica", make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))),
                        ("arvores", HistGradientBoostingClassifier(max_depth=3, learning_rate=0.02, max_iter=200,
                                                                   min_samples_leaf=300, random_state=0))):
            m.fit(x[cols][tr & mexeu], y[tr & mexeu])
            probas[nome] = m.predict_proba(x[cols])[:, 1]
        probas["contra a ultima vela"] = 0.5 - 0.2 * np.sign(x.ret1.to_numpy())
        for nome, p in probas.items():
            auc = roc_auc_score(y[te & mexeu], p[te & mexeu])
            # limiar escolhido pela media liquida no periodo de escolha, com pelo menos 100 operacoes
            notas = {lim: v.mean() for lim in LIMIARES if len(v := operar(p[va], x[va], lim, FEE_BPS[classe])) >= 100}
            if not notas:
                continue
            lim = max(notas, key=notas.get)
            for rotulo, mask in (("escolha", va), ("prova", te)):
                bruto_mid = np.where(p[mask] > 0.5 + lim, 1, np.where(p[mask] < 0.5 - lim, -1, 0)) * x.alvo_ret[mask]
                liq = operar(p[mask], x[mask], lim, FEE_BPS[classe])
                n = len(liq)
                print(f"{nome:>21} {rotulo:>7}: AUC {auc:.3f} limiar {lim:.2f} | {n:>5} ops | preco medio "
                      f"{bruto_mid.sum() / max(n, 1):>6.2f} bps | executavel liquido {liq.mean() if n else 0:>7.2f} "
                      f"bps/op | acerto {100 * (liq > 0).mean() if n else 0:.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--baixar", action="store_true")
    baixar() if ap.parse_args().baixar else testar()
