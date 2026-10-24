"""Ferramentas anti-autoengano (ver docs/conceitos/06_validacao_backtest.md)."""
from typing import Callable, Iterator

import numpy as np
import pandas as pd


def train_test_split_time(df: pd.DataFrame, test_start) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Corte temporal unico: o teste deve ser usado uma vez, com parametros ja fixados."""
    col = "datetime"
    cut = pd.Timestamp(test_start)
    return df[df[col] < cut].copy(), df[df[col] >= cut].copy()


def walk_forward_windows(index: pd.DatetimeIndex, train: str, test: str) -> Iterator[tuple[pd.Index, pd.Index]]:
    """Gera (idx_treino, idx_teste) deslizando; `train`/`test` sao offsets pandas, ex: '90D', '30D'."""
    train_off, test_off = pd.Timedelta(train), pd.Timedelta(test)
    start = index.min()
    while start + train_off + test_off <= index.max():
        mid = start + train_off
        yield index[(index >= start) & (index < mid)], index[(index >= mid) & (index < mid + test_off)]
        start += test_off


def bootstrap_trades(pnl: pd.Series, n_sims: int = 5000, seed: int = 0) -> dict:
    """Reamostra trades com reposicao: distribuicao de PnL final e drawdown maximo."""
    rng = np.random.default_rng(seed)
    arr = pnl.dropna().to_numpy()
    if arr.size == 0:
        return {}
    sims = rng.choice(arr, size=(n_sims, arr.size), replace=True)
    equity = sims.cumsum(axis=1)
    dd = (equity - np.maximum.accumulate(equity, axis=1)).min(axis=1)
    final = equity[:, -1]
    return {
        "pnl_p5": float(np.percentile(final, 5)),
        "pnl_p50": float(np.percentile(final, 50)),
        "pnl_p95": float(np.percentile(final, 95)),
        "prob_loss": float((final < 0).mean()),
        "dd_p50": float(np.percentile(dd, 50)),
        "dd_p95": float(np.percentile(dd, 5)),  # pior cenario (dd e negativo)
    }


def stress_costs(run: Callable[..., tuple[pd.DataFrame, dict]], factors=(1.0, 2.0, 3.0), **kwargs) -> pd.DataFrame:
    """Reroda o backtest multiplicando slippage e taxa; o edge sobrevive a custos pessimistas?"""
    rows = []
    base_slip = kwargs.pop("slippage_ticks", 1)
    for f in factors:
        _, m = run(slippage_ticks=base_slip * f, fee_scale=f, **kwargs)
        rows.append({"custo_x": f, **m})
    return pd.DataFrame(rows)
