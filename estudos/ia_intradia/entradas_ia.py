"""As operacoes reais da IA (Kalshi demo, 24 a 27/11/2026): onde perdem e se o momento de entrada vale algo.

1) Resultado por classe, lado e duracao, pelos numeros da corretora.
2) As mesmas entradas com saida fixa (15 min a 8 h, stop 2%), contra o mesmo ativo e lado em 40 horas sorteadas.
"""
import numpy as np
import pandas as pd
from comum import A, observ, operacoes_ia, t_blocos, velas

trips, fills = operacoes_ia()
preco = {}
for f in sorted(fills, key=lambda f: f["created_time"]):
    preco.setdefault((f["ticker"], round(observ.epoch(f["created_time"]), 3)), (float(f["price"]), float(f["count"])))
rows = []
for v in trips:
    p, q = preco[(v["ticker"], round(v["ini"], 3))]
    n = p * q
    rows.append(dict(cls=A.CATALOG.get(v["asset"], {}).get("cls"), lado="compra" if v["lado"] > 0 else "venda",
                     min=(v["fim"] - v["ini"]) / 60, bruto=v["bruto"] / n * 1e4, taxa=v["taxa"] / n * 1e4,
                     stop=v["corretora"], usd=v["bruto"] - v["taxa"]))
t = pd.DataFrame(rows)
t = t[t.bruto.abs() < 2000]
t["liq"] = t.bruto - t.taxa
t["dur"] = pd.cut(t["min"], [0, 15, 30, 60, 120, 1e9], labels=["<15m", "15-30m", "30-60m", "1-2h", ">2h"])
for col in ("cls", "lado", "dur", "stop"):
    g = t.groupby(col, observed=True).agg(n=("liq", "size"), acerto=("liq", lambda s: (s > 0).mean() * 100),
                                          bruto_bps=("bruto", "mean"), taxa_bps=("taxa", "mean"),
                                          liq_bps=("liq", "mean"), usd=("usd", "sum"))
    print(f"\n== IA por {col}\n{g.round(1).to_string()}")
print(f"\ntotal: {len(t)} operacoes, bruto medio {t.bruto.mean():.1f} bps, taxa {t.taxa.mean():.1f} bps")

bid, ask, mid, idx, cls, fee = velas()
rng = np.random.default_rng(1)


def resultado(a, i, lado, h, stop=2.0):
    """bps liquidos de entrar no minuto i (ask/bid) e sair h min depois, com stop conferido a cada minuto."""
    if i + h >= len(idx):
        return None
    ent = (ask[a] if lado > 0 else bid[a]).iloc[i]
    seg = (bid[a] if lado > 0 else ask[a]).iloc[i + 1:i + h + 1].dropna()
    if np.isnan(ent) or len(seg) == 0 or seg.index[-1] < idx[0] + i + h - 30:
        return None
    px = seg.iloc[-1]
    hit = seg[lado * (seg / ent - 1) <= -stop / 100]
    if len(hit):
        px = hit.iloc[0]
    return lado * (px / ent - 1) * 1e4 - 2 * fee[a]


H = [15, 60, 240, 480]
rows = []
for v in trips:
    a = v["asset"]
    if a not in mid:
        continue
    i = int(v["ini"] // 60) - int(idx[0]) + 1
    validos = np.flatnonzero(mid[a].notna().to_numpy())
    r = {"ini": v["ini"]}
    for h in H:
        r[f"h{h}"] = resultado(a, i, v["lado"], h)
        xs = [x for x in (resultado(a, int(j), v["lado"], h) for j in rng.choice(validos, 40)) if x is not None]
        r[f"p{h}"] = np.mean(xs) if xs else None
    rows.append(r)
e = pd.DataFrame(rows).astype(float)
print(f"\n== entradas reais com saida fixa (stop 2%), bps liquidos; {len(e)} entradas")
for h in H:
    s = e[[f"h{h}", f"p{h}"]].dropna()
    tt = t_blocos(s[f"h{h}"] - s[f"p{h}"], e.ini[s.index] // (max(h, 60) * 60))
    print(f"segurar {h:>3} min: n {len(s):3d} media {s[f'h{h}'].mean():7.1f} mediana {s[f'h{h}'].median():7.1f}"
          f"  hora sorteada {s[f'p{h}'].mean():7.1f}  t da diferenca {tt:5.1f}")
