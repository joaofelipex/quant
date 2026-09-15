"""Motor de backtest simples: uma posicao por vez, stop/alvo em multiplos de ATR."""
import pandas as pd

POINT_VALUE = 0.20  # R$ por ponto, 1 contrato de WIN
TICK_POINTS = 5  # 1 tick de WIN = 5 pontos


def run_backtest(
    df: pd.DataFrame,
    atr_stop_mult=1.5,
    risk_reward=2.0,
    contracts=1,
    slippage_ticks=1,
    fee_brl_round_trip=1.20,
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
                slippage_points = slippage_ticks * TICK_POINTS
                # slippage joga contra a posicao tanto na entrada quanto na saida
                effective_entry = position["entry_price"] + slippage_points * side
                effective_exit = exit_price - slippage_points * side
                pnl_points = (effective_exit - effective_entry) * side
                pnl_brl = pnl_points * POINT_VALUE * contracts - fee_brl_round_trip * contracts
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
    if trades_df.empty:
        return {"n_trades": 0}

    wins = trades_df[trades_df["pnl_brl"] > 0]
    losses = trades_df[trades_df["pnl_brl"] <= 0]
    equity = trades_df["pnl_brl"].cumsum()
    running_max = equity.cummax()
    drawdown = equity - running_max

    gross_win = wins["pnl_brl"].sum()
    gross_loss = losses["pnl_brl"].sum()

    return {
        "n_trades": len(trades_df),
        "win_rate": len(wins) / len(trades_df),
        "gross_pnl_brl": trades_df["pnl_brl"].sum(),
        "avg_win_brl": wins["pnl_brl"].mean() if len(wins) else 0.0,
        "avg_loss_brl": losses["pnl_brl"].mean() if len(losses) else 0.0,
        "profit_factor": (gross_win / abs(gross_loss)) if gross_loss != 0 else float("inf"),
        "max_drawdown_brl": drawdown.min(),
    }
