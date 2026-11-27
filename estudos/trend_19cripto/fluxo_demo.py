"""O desequilibrio do livro (imb_100) da Kalshi demo ajuda o robo a entrar? Roda NA VM, sobre as fotos de 1 min do
gravador (``/var/lib/quant/flow/*.csv``), so nas 19 criptos do robo.

1) quanto do tempo o filtro (QUANT_FLOW_MIN = 0,1: |imb_100| >= 0,1 a favor do lado) libera compra e venda, por ativo;
2) se o lado apontado pelo livro acerta o retorno de 15 min a 12 h (amostras sem sobreposicao), em bps e t;
3) retorno medio por quintil de imb_100.

    sudo -u quant env PYTHONPATH=/opt/quant/src /opt/quant/.venv/bin/python - < fluxo_demo.py
"""
import glob

import numpy as np
import pandas as pd

COINS = "BTC ETH SOL XRP BNB DOGE ADA LINK LTC BCH DOT NEAR UNI AAVE SUI XLM HBAR WLD ZEC".split()
df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob("/var/lib/quant/flow/*.csv"))])
df = df[df.asset.isin(COINS)]
df["ts"] = (df.ts // 60) * 60
df["mid"] = (df.bid + df.ask) / 2
mid = df.pivot_table(index="ts", columns="asset", values="mid", aggfunc="last").sort_index()
grid = np.arange(mid.index.min(), mid.index.max() + 60, 60)
mid = mid.reindex(grid)
imb = df.pivot_table(index="ts", columns="asset", values="imb_100", aggfunc="last").reindex(grid)
print(f"{len(grid)} minutos ({len(grid) / 1440:.1f} dias), {mid.shape[1]} ativos, "
      f"{pd.to_datetime(grid[0], unit='s')} a {pd.to_datetime(grid[-1], unit='s')}; fotos faltando "
      f"{imb.isna().mean().mean():.0%}")

st = pd.DataFrame({"media": imb.mean(), "dp": imb.std(), "libera_compra": (imb >= 0.1).mean(),
                   "libera_venda": (imb <= -0.1).mean(), "autocorr_1h": [imb[c].autocorr(60) for c in imb]})
print("\n## imb_100 por ativo")
print(st.round(2).to_string())
compra, venda = (imb >= 0.1).to_numpy().mean(), (imb <= -0.1).to_numpy().mean()
print(f"geral: libera compra {compra:.0%} do tempo, venda {venda:.0%}")


def pares(h):
    """imb_100 e retorno dos h minutos seguintes (bps), a cada h minutos, so onde os dois existem."""
    fwd = np.log(mid.shift(-h) / mid) * 1e4
    a, b = imb.iloc[::h].to_numpy().ravel(), fwd.iloc[::h].to_numpy().ravel()
    ok = ~np.isnan(a) & ~np.isnan(b)
    return pd.Series(a[ok]), pd.Series(b[ok]), fwd


print("\n## o lado do livro acerta o retorno seguinte? (so fotos com |imb| >= 0,1; sem sobreposicao)")
for h in (15, 60, 240, 720):
    a, b, fwd = pares(h)
    lado = np.sign(imb.where(imb.abs() >= 0.1))
    g = (lado * fwd).iloc[::h].to_numpy().ravel()
    g = g[~np.isnan(g)]
    por_t = (lado * fwd / fwd.std()).iloc[::h].mean(axis=1).dropna()  # media entre ativos por instante
    t = por_t.mean() / por_t.std() * np.sqrt(len(por_t)) if len(por_t) > 2 else float("nan")
    print(f"{h:>4} min: n {len(g):>5} | a favor do livro {g.mean():+6.1f} bps | acerto {(g > 0).mean():.0%} "
          f"| t {t:+.1f} ({len(por_t)} instantes) | IC {a.rank().corr(b.rank()):+.3f}")

print("\n## retorno medio (bps) por quintil de imb_100")
out = {}
for h in (60, 240):
    a, b, _ = pares(h)
    q = pd.qcut(a, 5, labels=False, duplicates="drop")
    out[f"{h} min"] = b.groupby(q).mean().round(1)
    out[f"imb medio {h}"] = a.groupby(q).mean().round(2)
print(pd.DataFrame(out).to_string())
