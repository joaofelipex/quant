"""Regras simples em 145 ativos, velas de 1 min da demo: seguir ou ir contra o movimento de 15 min a 1 dia.

Seguir: z > 1,5; contra: z > 2 (retorno / (vol de 1 min x raiz do prazo)). Entra 1 min depois do sinal no ask/bid,
segura 1 h, 4 h ou 1 dia, sem sobrepor operacoes do mesmo ativo, taxa taker por lado. Treino = 60% iniciais do tempo.
Ao final, as checagens das duas que passaram (atraso na entrada, sem os 3 melhores ativos, por dia).
"""
import numpy as np
import pandas as pd
from comum import t_blocos, velas

bid, ask, mid, idx, cls, fee = velas()
print("ativos:", mid.shape[1], "| dias:", round(len(idx) / 1440, 1))
corte = idx[0] + int(len(idx) * 0.6)
vol = ((mid / mid.shift(1) - 1) * 1e4).rolling(240, min_periods=100).std()


def operacoes(nomes, h_sig, h, direcao, z_min, atraso=1):
    ret = (mid / mid.shift(h_sig) - 1) * 1e4
    z = ret / (vol * np.sqrt(h_sig))
    out = []
    for a in nomes:
        s = (direcao * np.sign(ret[a])).where(z[a].abs() > z_min).to_numpy()
        b, k, last = bid[a].to_numpy(), ask[a].to_numpy(), -10**9
        for i in np.flatnonzero(~np.isnan(s)):
            j, f = i + atraso, i + atraso + h
            if i - last < h or f >= len(idx):
                continue
            ent, sai = (k[j], b[f]) if s[i] > 0 else (b[j], k[f])
            if np.isnan(ent) or np.isnan(sai):
                continue
            last = i
            liq = s[i] * (sai / ent - 1) * 1e4 - 2 * fee[a]
            if abs(liq) < 1500:
                out.append((idx[i], a, cls[a], s[i], liq))
    return pd.DataFrame(out, columns=["m", "ativo", "cls", "lado", "liq"])


res = []
for h_sig in (15, 60, 240, 1440):
    for nome, direcao, z_min in (("segue", 1, 1.5), ("contra", -1, 2.0)):
        for h in (60, 240, 1440):
            e = operacoes(list(mid), h_sig, h, direcao, z_min)
            for c, g in e.groupby("cls"):
                if len(g) < 60 or g.m.floordiv(max(h, 240)).nunique() < 8:
                    continue
                res.append(dict(regra=f"{nome} {h_sig}m", segura=h, classe=c, n=len(g), liq=g.liq.mean(),
                                treino=g[g.m < corte].liq.mean(), prova=g[g.m >= corte].liq.mean(),
                                t=t_blocos(g.liq, g.m // max(h, 240))))
r = pd.DataFrame(res)
ok = r[(r.treino > 0) & (r.prova > 0)]
print(f"\n{len(r)} combinacoes | positivas no treino {(r.treino > 0).sum()} | nos dois {len(ok)}"
      f" | e t>2 {(ok.t > 2).sum()}")
print(ok.sort_values("t", ascending=False).round(1).to_string(index=False))


def resumo(rotulo, e):
    tt = t_blocos(e.liq, e.m // 240)
    print(f"{rotulo}: n {len(e)} media {e.liq.mean():.1f} mediana {e.liq.median():.1f} acerto {(e.liq > 0).mean():.0%}"
          f" t {tt:.1f}")


for classe, h_sig in (("GPU", 60), ("Equities", 240)):
    nomes = [a for a in mid if cls[a] == classe]
    print(f"\n## contra {h_sig}m, segura {h_sig}m, {classe} ({len(nomes)} ativos)")
    for atraso in (1, 3, 10):
        resumo(f"entrada {atraso} min depois", operacoes(nomes, h_sig, h_sig, -1, 2.0, atraso))
    base = operacoes(nomes, h_sig, h_sig, -1, 2.0)
    top = base.groupby("ativo").liq.sum().nlargest(3).index
    if len(nomes) > 3:
        resumo("sem os 3 melhores ativos", base[~base.ativo.isin(top)])
    print("por lado:", base.groupby("lado").liq.mean().round(1).to_dict())
    print(base.groupby(pd.to_datetime(base.m * 60, unit="s").dt.strftime("%d/%m")).liq.mean().round(1).to_dict())
