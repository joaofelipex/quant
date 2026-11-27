"""A regra 'contra o movimento de 4 h' nas velas publicas de PRODUCAO da Kalshi (precos reais, sem chave), velas de 1 h.

Criterios fixados antes de olhar: mesma regra (z > 2, segura 4 h, sem sobreposicao), compra no ask e venda no bid,
taxa da classe por lado, entrada no fechamento da hora SEGUINTE ao sinal. A demo roda igual, para comparar.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from quant.agent import FEE_BPS  # noqa: E402
from quant.live import assets as A  # noqa: E402

D = Path(__file__).resolve().parents[2] / "dados" / "raw" / "kalshi_h1"
FIM = 1795752000  # 27/11/2026 12:00 UTC (reprodutivel)
INI = FIM - 400 * 86400


def baixar(env, host, a):
    out = D / env / f"{a}.csv"
    if out.exists():
        return
    ticker = A.ticker(a)
    if env == "producao":
        ticker = ticker.removesuffix("1")
    url = f"https://{host}/trade-api/v2/margin/markets/{ticker}/candlesticks"
    s, rows, t, passo = requests.Session(), [], INI, 290 * 3600
    while t < FIM:
        for n in range(8):
            try:
                r = s.get(f"{url}?period_interval=60&start_ts={t}&end_ts={min(t + passo, FIM)}", timeout=30)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(2 ** min(n, 5))
                    continue
                break
            except requests.RequestException:
                time.sleep(2 ** min(n, 5))
        else:
            return  # sem gravar: tenta de novo na proxima execucao
        if r.status_code != 200:
            break
        for c in r.json().get("candlesticks", []):
            try:
                rows.append((c["end_period_ts"] // 3600, float(c["bid"]["close"]), float(c["ask"]["close"])))
            except (KeyError, TypeError, ValueError):
                pass
        t += passo
    pd.DataFrame(rows, columns=["h", "bid", "ask"]).drop_duplicates("h").to_csv(out, index=False)


nomes = list(A.CATALOG)
for env, host in (("producao", "api.elections.kalshi.com"), ("demo", "external-api.demo.kalshi.co")):
    (D / env).mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda a: baixar(env, host, a), nomes))  # noqa: B023
    print(env, "arquivos", len(list((D / env).glob("*.csv"))), flush=True)

for env in ("producao", "demo"):
    quadro = {}
    for a in nomes:
        p = D / env / f"{a}.csv"
        if p.exists():
            d = pd.read_csv(p)
            d = d[(d.bid > 0) & (d.ask >= d.bid) & ((d.ask / d.bid - 1) < 0.005)]
            if len(d) >= 100:
                quadro[a] = d.set_index("h")
    if not quadro:
        print(env, "sem dados")
        continue
    idx = np.arange(min(d.index.min() for d in quadro.values()), FIM // 3600 + 1)
    bid = pd.DataFrame({a: d.bid.reindex(idx) for a, d in quadro.items()})
    ask = pd.DataFrame({a: d.ask.reindex(idx) for a, d in quadro.items()})
    mid = (bid + ask) / 2
    ret = (mid / mid.shift(4) - 1) * 1e4
    vol = ((mid / mid.shift(1) - 1) * 1e4).rolling(72, min_periods=24).std()
    z = ret / (vol * 2)
    ops = []
    for a in quadro:
        cls = A.CATALOG[a]["cls"]
        s = (-np.sign(ret[a])).where((z[a].abs() > 2) & (ret[a].abs() < 3000)).to_numpy()
        bi, ak, last = bid[a].to_numpy(), ask[a].to_numpy(), -99
        for i in np.flatnonzero(~np.isnan(s)):
            j, k = i + 1, i + 5
            if i - last < 4 or k >= len(idx):
                continue
            ent, sai = (ak[j], bi[k]) if s[i] > 0 else (bi[j], ak[k])
            if np.isnan(ent) or np.isnan(sai):
                continue
            last = i
            bruto = s[i] * (sai / ent - 1) * 1e4
            if abs(bruto) < 1500:
                ops.append((idx[i], a, cls, s[i], bruto - 2 * FEE_BPS.get(cls, 12)))
    e = pd.DataFrame(ops, columns=["h", "ativo", "cls", "lado", "liq"])
    print(f"\n######## {env}: {len(quadro)} ativos, {pd.to_datetime(idx[0] * 3600, unit='s'):%d/%m/%Y} a hoje")
    for cls, g in e.groupby("cls"):
        blk = g.groupby(g.h // 24).liq.mean()
        t = blk.mean() / (blk.std() / np.sqrt(len(blk))) if len(blk) > 4 else np.nan
        print(f"{cls:9s} n {len(g):5d} media {g.liq.mean():7.1f} mediana {g.liq.median():7.1f} acerto "
              f"{(g.liq > 0).mean():.0%} dias {len(blk):3d} t(por dia) {t:5.1f}")
    g = e[e.cls == "Equities"]
    if len(g):
        mes = g.groupby(pd.to_datetime(g.h * 3600, unit="s").dt.strftime("%Y-%U")).liq.agg(["size", "mean"])
        print("acoes por semana\n", mes.round(1).to_string())
