"""Variantes da receita (timeframe, ER, stop, saida por trailing, tamanho por volatilidade), treino x teste, custo 10 bps."""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\felip\projetos\quant\src")
from quant.strategies import trend_follow as tf

KL = Path(r"C:\Users\felip\AppData\Local\Temp\claude\ad2af04aa0604e8d\dae5c785-de2f-45a5-a779-cf2e68c81c00\scratchpad\klines")
COST = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0010
COINS = "BTC ETH SOL XRP BNB DOGE ADA LINK LTC BCH DOT NEAR UNI AAVE SUI XLM HBAR WLD ZEC".split()


def load(sym, tfm):
    d = pd.read_csv(KL / f"{sym}USDT_1h.csv", parse_dates=["datetime"])
    if tfm == "4h":
        d = (d.set_index("datetime").resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
             .dropna().reset_index())
    return d


def simulate(df, p):
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
                pos = {"s": pend[0], "e": o[j], "stop": o[j] - pend[0] * pend[1], "dist": pend[1], "t0": t[j], "w": w, "ext": o[j]}
            elif pend[0] == -pos["s"] and pend[1] == 0:
                trades.append((pos["t0"], t[j], (o[j] / pos["e"] - 1) * pos["s"] * pos["w"] - COST * pos["w"]))
                pos = None
            pend = None
        if pos is not None:
            s = pos["s"]
            hit = lo[j] <= pos["stop"] if s == 1 else h[j] >= pos["stop"]
            if hit:
                px = min(o[j], pos["stop"]) if s == 1 else max(o[j], pos["stop"])
                trades.append((pos["t0"], t[j], (px / pos["e"] - 1) * s * pos["w"] - COST * pos["w"]))
                pos = None
            elif p["trail"] > 0:
                pos["ext"] = max(pos["ext"], h[j]) if s == 1 else min(pos["ext"], lo[j])
                nstop = pos["ext"] - s * p["trail"] * pos["dist"] / p["stop"]
                pos["stop"] = max(pos["stop"], nstop) if s == 1 else min(pos["stop"], nstop)
        if sig[j] != 0 and np.isfinite(atr[j]) and atr[j] > 0:
            if pos is None:
                pend = (int(sig[j]), p["stop"] * atr[j], apct[j])
            elif sig[j] == -pos["s"] and not p["trail_only"]:
                pend = (int(sig[j]), 0, 0)
    return pd.DataFrame(trades, columns=["t0", "t1", "ret"])


def summarize(tr, n, start, end):
    if tr.empty:
        return dict(n=0, ret=0.0, exp=0.0, sh=0.0, dd=0.0, pf=0.0)
    day = pd.to_datetime(tr["t1"]).dt.floor("D")
    daily = tr["ret"].groupby(day.to_numpy()).sum()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.reindex(pd.date_range(pd.Timestamp(start).floor("D"), pd.Timestamp(end).floor("D")), fill_value=0.0) / n
    eq = daily.cumsum()
    w, l = tr.loc[tr.ret > 0, "ret"].sum(), -tr.loc[tr.ret <= 0, "ret"].sum()
    return dict(n=len(tr), ret=round(float(eq.iloc[-1]) * 100, 1), exp=round(float(tr.ret.mean()) * 1e4, 1),
                sh=round(float(daily.mean() / daily.std() * np.sqrt(365)), 2) if daily.std() > 0 else 0.0,
                dd=round(float((eq - eq.cummax()).min()) * 100, 1), pf=round(float(w / l), 2) if l > 0 else 9.9)


def main():
    res = []
    for tfm in ("1h", "4h"):
        data = {c: load(c, tfm) for c in COINS}
        t0 = max(d.datetime.min() for d in data.values())
        t1 = min(d.datetime.max() for d in data.values())
        mid = t0 + (t1 - t0) / 2
        print(f"{tfm}: {t0.date()} -> {t1.date()} corte {mid.date()}", flush=True)
        for er, stop, trail, vol in itertools.product((0.4, 0.5, 0.6), (2.0, 3.0), (0, 3.0), (False, True)):
            p = dict(dc=55, er=er, stop=stop, trail=trail, trail_only=False, vol=vol)
            a, b = [], []
            for c, d in data.items():
                tr = simulate(d[(d.datetime >= t0) & (d.datetime <= t1)].reset_index(drop=True), p)
                a.append(tr[tr.t1 < mid])
                b.append(tr[tr.t1 >= mid])
            res.append((tfm, er, stop, trail, vol, summarize(pd.concat(a), len(COINS), t0, mid),
                        summarize(pd.concat(b), len(COINS), mid, t1)))
    print("tf  er  stop trail vol | TREINO n ret% exp sharpe dd | TESTE n ret% exp sharpe dd pf")
    for r in sorted(res, key=lambda r: -r[5]["sh"]):
        tfm, er, st, tr_, vol, a, b = r
        print(f"{tfm} {er} {st} {tr_} {int(vol)} | {a['n']:>4} {a['ret']:>6} {a['exp']:>6} {a['sh']:>5} {a['dd']:>6} "
              f"| {b['n']:>4} {b['ret']:>6} {b['exp']:>6} {b['sh']:>5} {b['dd']:>6} {b['pf']:>4}")


if __name__ == "__main__":
    main()
