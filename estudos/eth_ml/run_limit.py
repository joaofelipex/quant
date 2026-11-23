"""eth_ml, ordens limitadas: o efeito de reversao sobrevive se entrarmos como maker em vez de pagar spread e taxa?

    python estudos/eth_ml/run_limit.py ETHUSDT        # tambem BTCUSDT, SOLUSDT

Sinal FIXO e pre-especificado (logit, m = 1,0%, d = 0,10, o melhor do ETH): nada e reotimizado aqui.
Simulacao por trade, um de cada vez, mantido H = 4 barras. Com barras OHLC nao ha fila nem profundidade, entao o
modelo de execucao e pessimista de proposito:

* Entrada limitada: ordem de compra (venda) em ``close[t]`` na barra seguinte; so executa se a minima (maxima) da barra
  ultrapassar o preco em ``through`` bps (toque nao conta). Sem execucao = sem trade (o movimento e perdido).
  Isso embute a selecao adversa: so somos executados quando o preco andou CONTRA nos.
* Saida limitada: ordem em ``open`` da barra de saida, mesma regra de execucao; se nao executar, sai a mercado no
  fechamento daquela barra (taker + slippage).
* Referencia: entrada e saida a mercado (taker 5 bps + slippage 2 bps por lado), mesmo sinal, mesma mecanica.

Variantes olhadas: maker {2, 5} bps x through {0, 2} bps x saida {mercado, limite} = 8, mais a referencia
e as 15 anteriores => N_TRIALS = 24.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_magnitude import walk_forward_scores  # noqa: E402
from run_study import PPY, REPORTS, H, load  # noqa: E402

from quant.metrics import sharpe  # noqa: E402
from quant.validation import deflated_sharpe_ratio  # noqa: E402

M, DELTA = 0.01, 0.10
TAKER_BPS, SLIP_BPS = 5.0, 2.0
N_TRIALS = 24


def simulate(df: pd.DataFrame, sig: np.ndarray, oos: np.ndarray, *, entry: str, exit_: str,
             maker_bps: float = 2.0, through_bps: float = 0.0) -> tuple[pd.Series, dict]:
    """Devolve (pnl por barra de saida, resumo). ``sig`` e +1/-1/0 por barra; ``oos`` marca barras avaliaveis."""
    o, h, lo, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(df)
    pnl = np.zeros(n)
    trades, signals, fills = [], 0, 0
    slip, thr = SLIP_BPS / 1e4, through_bps / 1e4
    i = 0
    while i < n - H - 3:
        if not oos[i] or sig[i] == 0:
            i += 1
            continue
        side = int(sig[i])
        signals += 1
        j = i + 1  # barra em que a ordem entra
        if entry == "market":
            px_in, fee_in = o[j] * (1 + side * slip), TAKER_BPS
        else:
            limit = c[i]
            hit = lo[j] < limit * (1 - thr) if side == 1 else h[j] > limit * (1 + thr)
            if not hit:
                i += 1
                continue
            px_in, fee_in = limit, maker_bps
        fills += 1
        k = j + H  # barra de saida
        if exit_ == "market":
            px_out, fee_out = o[k] * (1 - side * slip), TAKER_BPS
        else:
            limit2 = o[k]
            hit2 = h[k] > limit2 * (1 + thr) if side == 1 else lo[k] < limit2 * (1 - thr)
            if hit2:
                px_out, fee_out = limit2, maker_bps
            else:
                px_out, fee_out = c[k] * (1 - side * slip), TAKER_BPS
        net = side * (px_out - px_in) / px_in - (fee_in + fee_out) / 1e4
        pnl[k] += net
        trades.append(net)
        i = k + 1
    t = np.array(trades)
    info = {
        "sinais": signals, "execucao": fills / signals if signals else float("nan"), "trades": len(t),
        "bps_por_trade": float(t.mean() * 1e4) if len(t) else float("nan"),
        "win_rate": float((t > 0).mean()) if len(t) else float("nan"),
        "t_stat": float(t.mean() / t.std(ddof=1) * np.sqrt(len(t))) if len(t) > 2 and t.std() > 0 else float("nan"),
        "dsr_trade": deflated_sharpe_ratio(pd.Series(t), N_TRIALS) if len(t) > 2 else float("nan"),
    }
    return pd.Series(pnl, index=df.index), info


def main(symbol: str = "ETHUSDT") -> None:
    df = load(symbol)
    score = walk_forward_scores(df, "logit", M)
    s = score.reindex(df.index)
    sig = np.where(s > DELTA, 1, np.where(s < -DELTA, -1, 0))
    oos = s.notna().to_numpy()
    span = df.loc[oos]
    print(f"{symbol}: OOS {span['datetime'].min():%Y-%m-%d} a {span['datetime'].max():%Y-%m-%d}")

    configs = [("referencia_mercado", dict(entry="market", exit_="market"))]
    for maker in (2.0, 5.0):
        for thr in (0.0, 2.0):
            for ex in ("market", "limit"):
                configs.append((f"limite_maker{maker:.0f}_thr{thr:.0f}_saida_{ex}",
                                dict(entry="limit", exit_=ex, maker_bps=maker, through_bps=thr)))
    rows = []
    for name, kw in configs:
        pnl, info = simulate(df, sig, oos, **kw)
        rows.append({"variante": name, **info, "sharpe_barra": sharpe(pnl[oos], PPY)})
    table = pd.DataFrame(rows).set_index("variante").round(3)
    out = (
        f"# eth_ml - ordens limitadas ({symbol})\n\n"
        f"Sinal logit m=1,0% d=0,10; custo mercado {TAKER_BPS:.0f}+{SLIP_BPS:.0f} bps por lado; N_TRIALS={N_TRIALS} "
        "(DSR por trade). `execucao` = fracao de sinais em que a ordem limitada foi preenchida.\n\n"
        f"```\n{table.to_string()}\n```\n"
    )
    fname = "resultados_limite.md" if symbol == "ETHUSDT" else f"resultados_limite_{symbol}.md"
    (REPORTS / fname).write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ETHUSDT")
