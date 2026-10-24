"""Metricas de desempenho a partir de uma serie de PnL por trade ou de retornos por periodo."""
import numpy as np
import pandas as pd


def max_drawdown(pnl: pd.Series) -> float:
    equity = pnl.cumsum()
    return float((equity - equity.cummax()).min())


def trade_metrics(pnl: pd.Series) -> dict:
    """Metricas sobre PnL por trade (qualquer moeda)."""
    pnl = pnl.dropna()
    if pnl.empty:
        return {"n_trades": 0}
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    gross_loss = losses.sum()
    return {
        "n_trades": len(pnl),
        "win_rate": len(wins) / len(pnl),
        "total_pnl": float(pnl.sum()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "expectancy": float(pnl.mean()),
        "profit_factor": float(wins.sum() / abs(gross_loss)) if gross_loss != 0 else float("inf"),
        "max_drawdown": max_drawdown(pnl),
        "t_stat": float(pnl.mean() / pnl.std(ddof=1) * np.sqrt(len(pnl))) if len(pnl) > 1 and pnl.std() > 0 else 0.0,
    }


def sharpe(returns: pd.Series, periods_per_year: int = 252, rf_per_period: float = 0.0) -> float:
    ex = returns.dropna() - rf_per_period
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(periods_per_year)) if sd > 0 else 0.0


def sortino(returns: pd.Series, periods_per_year: int = 252, rf_per_period: float = 0.0) -> float:
    ex = returns.dropna() - rf_per_period
    downside = ex[ex < 0].std(ddof=1)
    return float(ex.mean() / downside * np.sqrt(periods_per_year)) if downside and downside > 0 else 0.0


def calmar(returns: pd.Series, periods_per_year: int = 252) -> float:
    equity = (1 + returns.dropna()).cumprod()
    dd = (equity / equity.cummax() - 1).min()
    ann = equity.iloc[-1] ** (periods_per_year / len(equity)) - 1
    return float(ann / abs(dd)) if dd < 0 else float("inf")
