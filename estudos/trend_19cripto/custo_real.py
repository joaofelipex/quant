"""O robo com o custo real da Kalshi: 35 bps ida e volta (12 + 12 bps de taxa a mercado + ~10 bps de spread) e o funding
da Binance. Compara a configuracao antiga (ER 0,4, trailing 3) com a atual (ER 0,5, sem trailing), por lado, e simula
o filtro de fluxo como uma porta aleatoria que libera a entrada na taxa medida na demo (``fluxo_demo.py``), por ativo e
lado.

Funding: soma das taxas nos instantes de liquidacao com a posicao aberta; comprado paga taxa positiva, vendido recebe.
Janela: ate o ultimo funding mensal publicado (31/10/2026).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.argv = sys.argv[:1]
import tune  # noqa: E402

tf = tune.tf
RAW = Path(__file__).resolve().parents[2] / "dados" / "raw" / "binance"
tune.KL = RAW / "h1_19"
COST = 0.0035
SORTEIOS = 200

# fracao das fotos do livro (25 a 27/11/2026) com |imb_100| >= 0,1 a favor do lado: (compra, venda)
PASSA = {"AAVE": (.30, .20), "ADA": (.52, .16), "BCH": (.56, .13), "BNB": (.37, .21), "BTC": (.66, .09),
         "DOGE": (.01, .00), "DOT": (.13, .09), "ETH": (.35, .31), "HBAR": (.17, .14), "LINK": (.06, .06),
         "LTC": (.07, .05), "NEAR": (.34, .17), "SOL": (.25, .53), "SUI": (.14, .10), "UNI": (.01, .01),
         "WLD": (.56, .19), "XLM": (.62, .13), "XRP": (.44, .39), "ZEC": (.13, .11)}
CONFIGS = {"atual (ER 0,5, sem trailing)": dict(dc=55, er=0.5, stop=2.0, trail=0, vol=True),
           "antiga (ER 0,4, trailing 3)": dict(dc=55, er=0.4, stop=2.0, trail=3.0, vol=True)}


def simulate(df, p, passa=None, rng=None):
    """Como ``tune.simulate``, mas devolve lado e peso de cada trade e aceita a porta de entrada aleatoria."""
    d = tf.add_indicators(df, donchian_period=p["dc"])
    d = tf.generate_signals(d, session_start="00:00", session_end="23:59", er_threshold=p["er"])
    o, h, lo, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sig, atr, t = d["signal"].to_numpy(int), d["atr"].to_numpy(float), d["datetime"].to_numpy()
    apct = atr / c
    ref = np.nanmedian(apct)
    trades, pos, pend = [], None, None
    for j in range(len(d)):
        if pend is not None:
            if pos is None:
                w = float(np.clip(ref / pend[2], 0.5, 2.0)) if p["vol"] and pend[2] > 0 else 1.0
                pos = {"s": pend[0], "e": o[j], "stop": o[j] - pend[0] * pend[1], "dist": pend[1], "t0": t[j], "w": w,
                       "ext": o[j]}
            elif pend[0] == -pos["s"] and pend[1] == 0:
                trades.append((pos["t0"], t[j], pos["s"], pos["w"], (o[j] / pos["e"] - 1) * pos["s"] * pos["w"]))
                pos = None
            pend = None
        if pos is not None:
            s = pos["s"]
            if (lo[j] <= pos["stop"]) if s == 1 else (h[j] >= pos["stop"]):
                px = min(o[j], pos["stop"]) if s == 1 else max(o[j], pos["stop"])
                trades.append((pos["t0"], t[j], s, pos["w"], (px / pos["e"] - 1) * s * pos["w"]))
                pos = None
            elif p["trail"] > 0:
                pos["ext"] = max(pos["ext"], h[j]) if s == 1 else min(pos["ext"], lo[j])
                nstop = pos["ext"] - s * p["trail"] * pos["dist"] / p["stop"]
                pos["stop"] = max(pos["stop"], nstop) if s == 1 else min(pos["stop"], nstop)
        if sig[j] != 0 and np.isfinite(atr[j]) and atr[j] > 0:
            if pos is None:
                if passa is None or rng.random() < passa[0 if sig[j] > 0 else 1]:  # o robo reconfere a cada barra
                    pend = (int(sig[j]), p["stop"] * atr[j], apct[j])
            elif sig[j] == -pos["s"]:
                pend = (int(sig[j]), 0, 0)
    return pd.DataFrame(trades, columns=["t0", "t1", "s", "w", "bruto"])


def funding_of(tr, f):
    """Funding de cada trade (fracao do capital): -lado x peso x soma das taxas com a posicao aberta."""
    ft = f.datetime.to_numpy("datetime64[ns]")
    cum = np.concatenate([[0.0], np.cumsum(f.funding_rate.to_numpy())])
    a = np.searchsorted(ft, tr.t0.to_numpy("datetime64[ns]"), side="right")
    b = np.searchsorted(ft, tr.t1.to_numpy("datetime64[ns]"), side="right")
    return -tr.s.to_numpy() * tr.w.to_numpy() * (cum[b] - cum[a])


data, fund = {}, {}
for c in tune.COINS:
    data[c] = tune.load(c, "1h")
    f = pd.read_csv(RAW / f"{c}USDT_funding.csv")
    f["datetime"] = pd.to_datetime(f.datetime).dt.tz_localize(None)
    fund[c] = f.sort_values("datetime").reset_index(drop=True)
t0 = max(d.datetime.min() for d in data.values())
t1 = min(min(d.datetime.max() for d in data.values()), min(f.datetime.max() for f in fund.values()))
mid = t0 + (t1 - t0) / 2
print(f"{t0.date()} -> {t1.date()}, corte {mid.date()}, custo {COST * 1e4:.0f} bps ida e volta")
fr = pd.concat([f[(f.datetime >= t0) & (f.datetime <= t1)].assign(c=c) for c, f in fund.items()])
print(f"funding medio: {fr.groupby('c').funding_rate.sum().mean() / ((t1 - t0).days / 365) * 100:.1f}% ao ano "
      "(o que um comprado parado pagaria)")


def run(p, rng=None):
    out = []
    for c, d in data.items():
        tr = simulate(d[(d.datetime >= t0) & (d.datetime <= t1)].reset_index(drop=True), p,
                      PASSA[c] if rng is not None else None, rng)
        if len(tr):
            out.append(tr.assign(fund=funding_of(tr, fund[c]), c=c))
    tr = pd.concat(out, ignore_index=True)
    return tr.assign(custo=-COST * tr.w)


def linha(rot, tr, col):
    x = tr.assign(ret=col(tr))
    a, b = tune.summarize(x[x.t1 < mid], 19, t0, mid), tune.summarize(x[x.t1 >= mid], 19, mid, t1)
    print(f"  {rot:<26} 1o ano {a['ret']:>6}% sh {a['sh']:>5} dd {a['dd']:>6}% | 2o ano {b['ret']:>6}% sh {b['sh']:>5} "
          f"dd {b['dd']:>6}% pf {b['pf']}")


for nome, p in CONFIGS.items():
    tr = run(p)
    fc, fv = tr[tr.s > 0].fund.mean() * 1e4, tr[tr.s < 0].fund.mean() * 1e4
    print(f"\n## {nome}: {len(tr)} trades; por trade: bruto {tr.bruto.mean() * 1e4:+.1f} bps, custo "
          f"{tr.custo.mean() * 1e4:+.1f}, funding {tr.fund.mean() * 1e4:+.1f} (comprado {fc:+.1f}, vendido {fv:+.1f}; "
          f"{(tr.s > 0).mean():.0%} comprados)")
    linha("sem funding", tr, lambda x: x.bruto + x.custo)
    linha("com funding", tr, lambda x: x.bruto + x.custo + x.fund)
    for lado, nm in ((1, "so comprado"), (-1, "so vendido")):
        linha(f"com funding, {nm}", tr[tr.s == lado], lambda x: x.bruto + x.custo + x.fund)

print(f"\n## atual + filtro de fluxo como porta aleatoria, {SORTEIOS} sorteios, com funding")
p = CONFIGS["atual (ER 0,5, sem trailing)"]
base = run(p)
res = []
for seed in range(SORTEIOS):
    tr = run(p, np.random.default_rng(seed))
    res.append((len(tr), (tr.bruto + tr.custo + tr.fund).sum() / 19 * 100))
r = pd.DataFrame(res, columns=["n", "ret"])
print(f"  sem filtro: {len(base)} trades, retorno total {(base.bruto + base.custo + base.fund).sum() / 19 * 100:+.1f}%")
print(f"  com filtro: {r.n.median():.0f} trades (mediana), retorno total mediana {r.ret.median():+.1f}%, "
      f"10% piores {r.ret.quantile(.1):+.1f}%, 10% melhores {r.ret.quantile(.9):+.1f}%, "
      f"negativos {(r.ret < 0).mean():.0%}")
