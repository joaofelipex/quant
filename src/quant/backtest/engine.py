"""Motor de backtest event-driven simples: uma posicao por vez, stop/alvo em multiplos de ATR.

Convencoes de execucao (todas pessimistas ou neutras, nunca otimistas):

* ``entry="next_open"`` (padrao): o sinal e calculado com o fechamento da barra *i* e a ordem so
  entra na abertura da barra *i+1*. ``entry="close"`` reproduz o modo legado (entra no proprio
  fechamento do sinal, que na pratica e look-ahead de uma barra).
* Stop e ordem a mercado: paga slippage e, se a barra abre alem do stop (gap), sai na abertura.
* Alvo e ordem limitada: sem slippage; se a barra abre alem do alvo, sai na abertura (a favor).
* Se stop e alvo caem na mesma barra, assume-se o stop (pior caso).
* ``force_flat`` zera a posicao a mercado no horario indicado; posicao nunca atravessa a noite.

O contrato vem de ``quant.instruments.Instrument``; o motor nao conhece nenhum ativo.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from quant.instruments import WIN, Instrument
from quant.metrics import trade_metrics

_MARKET_EXITS = {"stop", "stop_gap", "eod", "overnight"}


def _parse_time(value: str | dt.time | None) -> dt.time | None:
    if value is None or isinstance(value, dt.time):
        return value
    return dt.datetime.strptime(value, "%H:%M").time()


def run_backtest(
    df: pd.DataFrame,
    atr_stop_mult: float = 1.5,
    risk_reward: float = 2.0,
    contracts: int = 1,
    slippage_ticks: float = 1,
    instrument: Instrument = WIN,
    fee_scale: float = 1.0,
    entry: str = "next_open",
    force_flat: str | dt.time | None = "17:50",
    stop_col: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Simula a estrategia descrita por ``df['signal']`` (+1/-1/0) e ``df['atr']``.

    A distancia do stop e ``atr * atr_stop_mult``; se ``stop_col`` for dado, usa-se essa coluna (em pontos)
    no lugar do ATR (stop fixo em pontos, como nos robos NTSL). O alvo e sempre ``risk_reward`` x o stop.

    Retorna (trades, metricas). ``fee_scale`` multiplica a taxa fixa (usado em ``stress_costs``).
    """
    if entry not in {"next_open", "close"}:
        raise ValueError("entry deve ser 'next_open' ou 'close'")
    flat_time = _parse_time(force_flat)

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    sig = df["signal"].to_numpy(int)
    dist_arr = df[stop_col].to_numpy(float) if stop_col else df["atr"].to_numpy(float) * atr_stop_mult
    when = df["datetime"].to_numpy()
    days = df["datetime"].dt.date.to_numpy()
    times = df["datetime"].dt.time.to_numpy()

    slip = slippage_ticks * instrument.tick_size
    fee = instrument.fee_round_trip * fee_scale * contracts
    mult = instrument.point_value * contracts

    trades: list[dict] = []
    pos = None  # dict(side, entry, stop, target, time, day, bar)
    pending = None  # (side, stop_dist) decidido no fechamento da barra anterior

    def close_trade(j: int, raw_exit: float, reason: str) -> None:
        nonlocal pos
        side = pos["side"]
        eff_entry = pos["entry"] + slip * side
        eff_exit = raw_exit - slip * side if reason in _MARKET_EXITS else raw_exit
        pnl_points = (eff_exit - eff_entry) * side
        trades.append({
            "entry_time": pos["time"],
            "exit_time": when[j],
            "side": "long" if side == 1 else "short",
            "entry_price": pos["entry"],
            "exit_price": raw_exit,
            "reason": reason,
            "bars": j - pos["bar"],
            "pnl_points": pnl_points,
            "pnl_brl": pnl_points * mult - fee,
        })
        pos = None

    def open_trade(j: int, price: float, side: int, dist: float) -> None:
        nonlocal pos
        pos = {
            "side": side, "entry": price, "time": when[j], "day": days[j], "bar": j,
            "stop": price - side * dist, "target": price + side * dist * risk_reward,
        }

    n = len(df)
    for j in range(n):
        # (a) entrada pendente do fechamento anterior
        if pending is not None:
            side, dist = pending
            pending = None
            same_day = j > 0 and days[j] == days[j - 1]
            before_flat = flat_time is None or times[j] < flat_time
            if pos is None and same_day and before_flat:
                open_trade(j, o[j], side, dist)

        if pos is not None:
            # (b) zeragem forcada / virada de dia (nao dormir posicionado)
            if days[j] != pos["day"]:
                close_trade(j, o[j], "overnight")
            elif flat_time is not None and times[j] >= flat_time:
                close_trade(j, o[j], "eod")

        if pos is not None:
            # (c) stop / alvo dentro da barra
            side, stop, target = pos["side"], pos["stop"], pos["target"]
            if side == 1:
                gap_stop, hit_stop, hit_tgt = o[j] <= stop, lo[j] <= stop, h[j] >= target
                gap_tgt = o[j] >= target
            else:
                gap_stop, hit_stop, hit_tgt = o[j] >= stop, h[j] >= stop, lo[j] <= target
                gap_tgt = o[j] <= target
            if gap_stop:
                close_trade(j, o[j], "stop_gap")
            elif hit_stop:  # inclui stop e alvo na mesma barra -> pior caso
                close_trade(j, stop, "stop")
            elif gap_tgt:
                close_trade(j, o[j], "target")
            elif hit_tgt:
                close_trade(j, target, "target")

        # (d) novo sinal (so se flat apos processar a barra)
        if pos is None and sig[j] != 0 and np.isfinite(dist_arr[j]):
            dist = dist_arr[j]
            if entry == "close":
                open_trade(j, c[j], int(sig[j]), dist)
            else:
                pending = (int(sig[j]), dist)

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["equity_brl"] = trades_df["pnl_brl"].cumsum()
    return trades_df, compute_metrics(trades_df)


def compute_metrics(trades_df: pd.DataFrame) -> dict:
    """Metricas legadas (chaves *_brl) sobre trade_metrics, para manter os relatorios existentes."""
    if trades_df.empty:
        return {"n_trades": 0}
    m = trade_metrics(trades_df["pnl_brl"])
    return {
        "n_trades": m["n_trades"],
        "win_rate": m["win_rate"],
        "gross_pnl_brl": m["total_pnl"],
        "avg_win_brl": m["avg_win"],
        "avg_loss_brl": m["avg_loss"],
        "profit_factor": m["profit_factor"],
        "max_drawdown_brl": m["max_drawdown"],
        "t_stat": m["t_stat"],
    }
