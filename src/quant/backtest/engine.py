"""Motor de backtest simples: uma posicao por vez, stop/alvo em multiplos de ATR.

Agnostico de ativo: o contrato vem de `quant.instruments.Instrument` (default WIN).
"""
import pandas as pd

from quant.instruments import Instrument, WIN
from quant.metrics import trade_metrics


def run_backtest(
    df: pd.DataFrame,
    atr_stop_mult=1.5,
    risk_reward=2.0,
    contracts=1,
    slippage_ticks=1,
    instrument: Instrument = WIN,
    fee_scale=1.0,
) -> tuple[pd.DataFrame, dict]:
    trades = []
    position = None  # dict: side, entry_price, stop, target, entry_time

    for _, row in df.iterrows():
        if position is not None:
            side = position["side"]
            hit_stop = (row["low"] <= position["stop"]) if side == 1 else (row["high"] >= position["stop"])
            hit_target = (row["high"] >= position["target"]) if side == 1 else (row["low"] <= position["target"])

            exit_price = None
            reason = None
            if hit_stop and hit_target:
                exit_price, reason = position["stop"], "stop"  # pior caso conservador
            elif hit_stop:
                exit_price, reason = position["stop"], "stop"
            elif hit_target:
                exit_price, reason = position["target"], "target"

            if exit_price is not None:
                slippage_points = slippage_ticks * instrument.tick_size
                # slippage joga contra a posicao tanto na entrada quanto na saida
                effective_entry = position["entry_price"] + slippage_points * side
                effective_exit = exit_price - slippage_points * side
                pnl_points = (effective_exit - effective_entry) * side
                pnl_brl = pnl_points * instrument.point_value * contracts - instrument.fee_round_trip * fee_scale * contracts
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": row["datetime"],
                    "side": "long" if side == 1 else "short",
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "reason": reason,
                    "pnl_points": pnl_points,
                    "pnl_brl": pnl_brl,
                })
                position = None

        if position is None and row["signal"] != 0 and pd.notna(row["atr"]):
            side = row["signal"]
            entry_price = row["close"]
            stop_dist = row["atr"] * atr_stop_mult
            stop = entry_price - stop_dist * side
            target = entry_price + stop_dist * risk_reward * side
            position = {
                "side": side,
                "entry_price": entry_price,
                "stop": stop,
                "target": target,
                "entry_time": row["datetime"],
            }

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["equity_brl"] = trades_df["pnl_brl"].cumsum()
    metrics = compute_metrics(trades_df)
    return trades_df, metrics


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
