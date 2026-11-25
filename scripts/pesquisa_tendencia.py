# ruff: noqa: E501
"""Pesquisa: a estrategia de tendencia do repo tem vantagem em cripto, com custos, FORA da amostra?

    python scripts/pesquisa_tendencia.py [1h] [730] [0.0010]     # intervalo, dias, custo ida e volta (fracao)

Escolhe a configuracao so pelo 1o ano e mede no 2o. Resultado de 2026-11-25 (19 cripto, 1h, 10 bps): ER 0,5 / canal 55 / stop 2 ATR,
comprado e vendido: teste +38%, Sharpe 1,45, t=2,2; so comprado: +11%, t=0,74 (nao significativo). Ver deploy/README.md.
"""
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quant.live import assets
from quant.strategies import trend_follow as tf

CACHE = Path(__file__).resolve().parents[1] / "dados" / "raw" / "pesquisa_tendencia"
CACHE.mkdir(exist_ok=True)
INTERVAL = sys.argv[1] if len(sys.argv) > 1 else "1h"
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 730
COST_RT = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0010  # 10 bps ida e volta (taxa + slippage)
STEP = {"1h": 3600_000, "15m": 900_000, "4h": 14_400_000}[INTERVAL]


def klines(sym: str) -> pd.DataFrame:
    f = CACHE / f"{sym}_{INTERVAL}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["datetime"])
    end = int(time.time() * 1000)
    start = end - DAYS * 86400_000
    rows = []
    while start < end:
        r = requests.get("https://data-api.binance.vision/api/v3/klines",
                         params={"symbol": sym, "interval": INTERVAL, "startTime": start, "limit": 1000}, timeout=30)
        r.raise_for_status()
        b = r.json()
        if not b:
            break
        rows += b
        start = b[-1][0] + STEP
        if len(b) < 1000:
            break
    df = pd.DataFrame({"datetime": pd.to_datetime([x[0] for x in rows], unit="ms"),
                       "open": [float(x[1]) for x in rows], "high": [float(x[2]) for x in rows],
                       "low": [float(x[3]) for x in rows], "close": [float(x[4]) for x in rows]})
    df = df.drop_duplicates("datetime").iloc[:-1]  # tira a barra em formacao
    df.to_csv(f, index=False)
    return df


def simulate(df: pd.DataFrame, p: dict, long_only: bool) -> pd.DataFrame:
    """Barra a barra: sinal no fechamento -> entra na abertura seguinte; stop ATR; sai no sinal oposto (abertura seguinte)."""
    d = tf.add_indicators(df, ema_fast=p["ef"], ema_slow=p["es"], donchian_period=p["dc"], er_period=p["erp"])
    d = tf.generate_signals(d, session_start="00:00", session_end="23:59", er_threshold=p["er"])
    o, h, lo, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sig, atr = d["signal"].to_numpy(int), d["atr"].to_numpy(float)
    t = d["datetime"].to_numpy()
    trades, pos, pend = [], None, None
    for j in range(len(d)):
        if pend is not None:
            if pos is None:
                pos = {"side": pend[0], "entry": o[j], "stop": o[j] - pend[0] * pend[1], "t0": t[j], "j0": j}
            elif pend[0] == -pos["side"] and pend[1] == 0:  # saida por sinal oposto, na abertura
                trades.append((pos["t0"], t[j], pos["side"], (o[j] / pos["entry"] - 1) * pos["side"] - COST_RT, "sinal"))
                pos = None
            pend = None
        if pos is not None:
            s = pos["side"]
            hit = lo[j] <= pos["stop"] if s == 1 else h[j] >= pos["stop"]
            if hit:
                px = min(o[j], pos["stop"]) if s == 1 else max(o[j], pos["stop"])
                trades.append((pos["t0"], t[j], s, (px / pos["entry"] - 1) * s - COST_RT, "stop"))
                pos = None
        if sig[j] != 0 and np.isfinite(atr[j]):
            if pos is None and not (long_only and sig[j] < 0):
                pend = (int(sig[j]), p["stop"] * atr[j])
            elif pos is not None and sig[j] == -pos["side"]:
                pend = (int(sig[j]), 0)
    return pd.DataFrame(trades, columns=["t0", "t1", "side", "ret", "why"])


def summarize(tr: pd.DataFrame, n_assets: int, start, end) -> dict:
    if tr.empty:
        return {"n": 0, "ret_total_pct": 0.0, "exp_bps": 0.0, "hit": 0.0, "pf": 0.0, "sharpe": 0.0, "maxdd_pct": 0.0}
    tr = tr.sort_values("t1")
    day = pd.to_datetime(tr["t1"]).dt.floor("D")
    daily = tr["ret"].groupby(day.to_numpy()).sum()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.reindex(pd.date_range(pd.Timestamp(start).floor("D"), pd.Timestamp(end).floor("D"), freq="1D"), fill_value=0.0) / n_assets
    eq = daily.cumsum()
    wins, losses = tr.loc[tr.ret > 0, "ret"].sum(), -tr.loc[tr.ret <= 0, "ret"].sum()
    return {"n": len(tr), "ret_total_pct": round(float(eq.iloc[-1]) * 100, 2), "exp_bps": round(float(tr.ret.mean()) * 1e4, 1),
            "hit": round(float((tr.ret > 0).mean()), 3), "pf": round(float(wins / losses), 2) if losses > 0 else float("inf"),
            "sharpe": round(float(daily.mean() / daily.std() * np.sqrt(365)), 2) if daily.std() > 0 else 0.0,
            "maxdd_pct": round(float((eq - eq.cummax()).min()) * 100, 2)}


def main():
    syms = [a + "USDT" for a in assets.CRYPTO]
    data = {s: klines(s) for s in syms}
    ok = {s: d for s, d in data.items() if len(d) > 0.9 * max(len(x) for x in data.values())}  # tira moedas com pouco historico
    print(f"{len(ok)} ativos, {INTERVAL}, ~{DAYS} dias, custo ida e volta {COST_RT * 1e4:.0f} bps")
    t_min = max(d["datetime"].min() for d in ok.values())
    t_max = min(d["datetime"].max() for d in ok.values())
    mid = t_min + (t_max - t_min) / 2
    print("periodo comum:", t_min.date(), "->", t_max.date(), "| corte treino/teste:", mid.date())

    # buy & hold igual-peso (referencia)
    bh = []
    for d in ok.values():
        x = d[(d.datetime >= t_min) & (d.datetime <= t_max)]
        bh.append(x.close.iloc[-1] / x.close.iloc[0] - 1)
    bh_t = []
    for d in ok.values():
        x = d[(d.datetime >= mid) & (d.datetime <= t_max)]
        bh_t.append(x.close.iloc[-1] / x.close.iloc[0] - 1)
    print(f"buy&hold igual-peso: periodo todo {np.mean(bh) * 100:+.1f}% | so a metade final (teste) {np.mean(bh_t) * 100:+.1f}%")

    grid = [dict(er=er, dc=dc, stop=st, ef=9, es=21, erp=20) for er, dc, st in itertools.product((0.3, 0.5), (20, 55), (2.0, 4.0))]
    res = []
    for p in grid:
        for lo_ in (True, False):
            tr_train, tr_test = [], []
            for s, d in ok.items():
                d = d[(d.datetime >= t_min) & (d.datetime <= t_max)].reset_index(drop=True)
                tr = simulate(d, p, lo_)
                tr["a"] = s
                tr_train.append(tr[tr.t1 < mid])
                tr_test.append(tr[tr.t1 >= mid])
            a, b = pd.concat(tr_train), pd.concat(tr_test)
            res.append({**p, "long_only": lo_, "train": summarize(a, len(ok), t_min, mid), "test": summarize(b, len(ok), mid, t_max)})
    print("\nconfig (er, dc, stop, long_only)  |  TREINO: n  ret%  exp_bps  sharpe |  TESTE: n  ret%  exp_bps  hit  pf  sharpe  maxdd%")
    for r in sorted(res, key=lambda r: -r["train"]["sharpe"]):
        a, b = r["train"], r["test"]
        print(f"er={r['er']} dc={r['dc']} st={r['stop']} {'long ' if r['long_only'] else 'both '}| {a['n']:>5} {a['ret_total_pct']:>7} {a['exp_bps']:>6} {a['sharpe']:>5} "
              f"| {b['n']:>5} {b['ret_total_pct']:>7} {b['exp_bps']:>6} {b['hit']:>5} {b['pf']:>5} {b['sharpe']:>5} {b['maxdd_pct']:>6}")
    best = max(res, key=lambda r: r["train"]["sharpe"])
    print("\nescolhida SO pelo treino:", {k: best[k] for k in ("er", "dc", "stop", "long_only")})
    print("resultado no TESTE (fora da amostra):", best["test"])
    n = len(res)
    print(f"({n} configuracoes testadas: o melhor do treino sempre parece bom; so vale o que sobrou no teste)")


if __name__ == "__main__":
    main()
