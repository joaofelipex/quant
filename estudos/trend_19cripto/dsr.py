import sys
import numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\felip\projetos\quant\src")
import tune
from quant.validation import deflated_sharpe_ratio, probabilistic_sharpe_ratio, expected_max_sharpe

CONFIGS = {
 "base (ER .5, stop 2)":      dict(dc=55, er=0.5, stop=2.0, trail=0, trail_only=False, vol=False),
 "final (ER .5, trail 3, vol)": dict(dc=55, er=0.5, stop=2.0, trail=3.0, trail_only=False, vol=True),
}
data = {c: tune.load(c, "1h") for c in tune.COINS}
t0 = max(d.datetime.min() for d in data.values()); t1 = min(d.datetime.max() for d in data.values())
mid = t0 + (t1 - t0) / 2
days = pd.date_range(mid.floor("D"), t1.floor("D"))
for name, p in CONFIGS.items():
    trs = []
    for c, d in data.items():
        tr = tune.simulate(d[(d.datetime >= t0) & (d.datetime <= t1)].reset_index(drop=True), p)
        trs.append(tr[tr.t1 >= mid])
    tr = pd.concat(trs)
    daily = tr.groupby(pd.to_datetime(tr.t1).dt.floor("D"))["ret"].sum().reindex(days, fill_value=0.0) / len(tune.COINS)
    sr_d = daily.mean() / daily.std()
    print(f"\n{name}: {len(tr)} trades, {len(daily)} dias, Sharpe anual {sr_d*np.sqrt(365):.2f}, retorno {daily.sum()*100:.1f}%")
    print(f"  PSR(SR>0) diario: {probabilistic_sharpe_ratio(daily):.3f} | por trade: {probabilistic_sharpe_ratio(tr.ret):.3f}")
    for n in (16, 64, 100):
        print(f"  DSR com {n:>3} tentativas: diario {deflated_sharpe_ratio(daily, n):.3f} | por trade {deflated_sharpe_ratio(tr.ret, n):.3f}"
              f" | Sharpe do acaso (diario, anual) {expected_max_sharpe(n, 1/(len(daily)-1))*np.sqrt(365):.2f}")
