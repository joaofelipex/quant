"""eth_ml, rotulo de magnitude: so operar quando o modelo espera um movimento maior que o custo.

    python estudos/eth_ml/run_magnitude.py        # depois de baixar os dados (ver run_study.py)

Rotulo de 3 classes sobre o retorno de H = 4 barras (entrada na abertura seguinte): +1 se > m, -1 se < -m, 0 no meio.
Posicao = +1 se P(+1) - P(-1) > d, -1 se < -d, senao zero. Mesmo walk-forward, purga e custos do run_study.
Variantes olhadas: 2 modelos x m in (0,5%, 1,0%) x d in (0,05, 0,10) = 8, mais as 7 do run_study => N_TRIALS = 15.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_study import FEATURES, PPY, REPORTS, TEST, TRAIN, H, load, net_returns, new_model, stats  # noqa: E402

from quant.metrics import sharpe  # noqa: E402
from quant.validation import deflated_sharpe_ratio, walk_forward_splits  # noqa: E402

MAGNITUDES = (0.005, 0.01)
DELTAS = (0.05, 0.10)
N_TRIALS = 15


def walk_forward_scores(df: pd.DataFrame, model: str, m: float) -> pd.Series:
    """Score = P(+1) - P(-1) fora da amostra."""
    purge = pd.Timedelta(hours=int(H + 1))
    out = []
    for tr, te in walk_forward_splits(df, TRAIN, TEST):
        tr = tr[tr["datetime"] < te["datetime"].min() - purge].dropna(subset=[*FEATURES, "fwd"])
        te = te.dropna(subset=FEATURES)
        y = np.where(tr["fwd"] > m, 1, np.where(tr["fwd"] < -m, -1, 0))
        clf = new_model(model).fit(tr[FEATURES], y)
        p = pd.DataFrame(clf.predict_proba(te[FEATURES]), columns=clf.classes_, index=te.index)
        out.append(p.get(1, 0.0) - p.get(-1, 0.0))
    return pd.concat(out)


def main(symbol: str = "ETHUSDT") -> None:
    df = load(symbol)
    rows, nets = [], {}
    for mname in ("logit", "gbm"):
        for m in MAGNITUDES:
            score = walk_forward_scores(df, mname, m)
            oos = score.index.intersection(df.index[df["ret1"].notna()])
            d, s = df.loc[oos], score.loc[oos]
            share = float(((d["fwd"].abs() > m) & d["fwd"].notna()).mean())
            for delta in DELTAS:
                pos = pd.Series(np.where(s > delta, 1.0, np.where(s < -delta, -1.0, 0.0)), index=oos)
                net = net_returns(pos, d["ret1"])
                name = f"{mname}_m{m * 100:.1f}%_d{delta:.2f}"
                nets[name] = net
                row = {"variante": name, **stats(net, pos)}
                row["sharpe_bruto"] = sharpe(pos * d["ret1"], PPY)
                row["sharpe_x2"] = sharpe(net_returns(pos, d["ret1"], 2.0), PPY)
                row["dsr"] = deflated_sharpe_ratio(net, N_TRIALS)
                row["barras_com_|fwd|>m"] = share
                rows.append(row)
    table = pd.DataFrame(rows).set_index("variante").round(3)
    out = (
        "# eth_ml - rotulo de magnitude (OOS)\n\n"
        f"N_TRIALS={N_TRIALS} no DSR (por barra, otimista). Custo 7 bps por lado.\n\n```\n{table.to_string()}\n```\n"
    )
    fname = "resultados_magnitude.md" if symbol == "ETHUSDT" else f"resultados_magnitude_{symbol}.md"
    (REPORTS / fname).write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ETHUSDT")
