"""
Scalper de fluxo (agressao) para ETH futuro B3 - baseado em times & trades.

ATENCAO: validado com apenas 1 dia de dado (09:00-19:10).
NAO tem validacao out-of-sample. NAO deve ser usado em conta real,
nem simulada, ate ter pelo menos 10-15 dias de dado para validar
que o edge nao e apenas ruido de um dia especifico.

Parametros abaixo (window=50, threshold=0.5, target=8, stop=5) foram
os que melhor equilibraram numero de trades vs resultado no unico dia
testado -- profit factor 1.57 sobre 43 trades. Isso pode nao se repetir.
"""
import pandas as pd
import numpy as np


def load_times_trades(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]
    df["Valor"] = (
        df["Valor"].str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    df["Quantidade"] = df["Quantidade"].astype(int)
    df["dt"] = pd.to_datetime(df["Data"], format="%H:%M:%S.%f")
    df = df.sort_values("dt").reset_index(drop=True)
    df["vol_sinal"] = np.where(df["Agressor"] == "Comprador", df["Quantidade"], -df["Quantidade"])
    return df


def backtest_flow_scalper(
    df: pd.DataFrame,
    window: int = 50,
    threshold: float = 0.5,
    target_pts: float = 8.0,
    stop_pts: float = 5.0,
    slippage: float = 0.5,
) -> tuple[pd.DataFrame, dict]:
    imbalance = df["vol_sinal"].rolling(window).sum()
    vol_total = df["Quantidade"].rolling(window).sum()
    ratio = imbalance / vol_total

    position = None
    trades = []

    for i in range(len(df)):
        row = df.iloc[i]

        if position is not None:
            side = position["side"]
            move = (row["Valor"] - position["entry"]) * side
            exit_price = None
            reason = None
            if move <= -stop_pts:
                exit_price = position["entry"] - stop_pts * side
                reason = "stop"
            elif move >= target_pts:
                exit_price = position["entry"] + target_pts * side
                reason = "target"
            if exit_price is not None:
                pnl_usd = (target_pts if reason == "target" else -stop_pts) - slippage
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": row["dt"],
                    "side": "compra" if side == 1 else "venda",
                    "entry_price": position["entry"],
                    "reason": reason,
                    "pnl_usd": pnl_usd,
                })
                position = None

        if position is None and not np.isnan(ratio.iloc[i]):
            r = ratio.iloc[i]
            if r >= threshold:
                position = {"side": 1, "entry": row["Valor"], "entry_time": row["dt"]}
            elif r <= -threshold:
                position = {"side": -1, "entry": row["Valor"], "entry_time": row["dt"]}

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["equity_usd"] = trades_df["pnl_usd"].cumsum()

    metrics = compute_metrics(trades_df)
    return trades_df, metrics


def compute_metrics(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {"n_trades": 0}
    wins = trades_df[trades_df["pnl_usd"] > 0]
    losses = trades_df[trades_df["pnl_usd"] <= 0]
    gross_win = wins["pnl_usd"].sum()
    gross_loss = losses["pnl_usd"].sum()
    equity = trades_df["pnl_usd"].cumsum()
    drawdown = equity - equity.cummax()
    return {
        "n_trades": len(trades_df),
        "win_rate": len(wins) / len(trades_df),
        "pnl_total_usd": trades_df["pnl_usd"].sum(),
        "profit_factor": (gross_win / abs(gross_loss)) if gross_loss != 0 else float("inf"),
        "max_drawdown_usd": drawdown.min(),
    }


if __name__ == "__main__":
    from pathlib import Path

    data_path = Path(__file__).resolve().parents[1] / "data" / "eth_times_trades.csv"
    df = load_times_trades(str(data_path))
    trades_df, metrics = backtest_flow_scalper(df)

    print(f"Periodo: {df['dt'].min()} a {df['dt'].max()} (1 dia apenas)")
    print(f"Negocios no book: {len(df)}")
    print("---")
    for k, v in metrics.items():
        print(f"{k}: {v}")

    out_path = Path(__file__).resolve().parents[1] / "reports" / "eth_flow_trades.csv"
    trades_df.to_csv(out_path, index=False)
    print(f"\nTrades salvos em {out_path}")
    print("\nLEMBRETE: 1 dia de dado nao valida edge. Nao rodar em conta real/simulada ainda.")
