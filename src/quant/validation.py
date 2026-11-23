"""Ferramentas anti-autoengano (ver docs/conceitos/06_validacao_backtest.md)."""
from collections.abc import Callable, Iterator, Sequence
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
_EULER_GAMMA = 0.5772156649015329


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


def walk_forward_splits(df: pd.DataFrame, train: str, test: str) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
    """Janelas (treino, teste) deslizantes sobre ``df['datetime']``; passo = tamanho do teste.

    Os periodos de teste sao disjuntos e consecutivos: concatenados formam a serie OOS.
    """
    t = df["datetime"]
    train_off, test_off = pd.Timedelta(train), pd.Timedelta(test)
    start = t.min()
    while start + train_off + test_off <= t.max():
        mid = start + train_off
        yield df[(t >= start) & (t < mid)], df[(t >= mid) & (t < mid + test_off)]
        start += test_off


def probabilistic_sharpe_ratio(pnl: pd.Series, sr_benchmark: float = 0.0) -> float:
    """PSR (Bailey & Lopez de Prado): P(Sharpe verdadeiro > benchmark), por trade, ajustado a skew/kurtosis."""
    x = pnl.dropna()
    n = len(x)
    if n < 3 or x.std(ddof=1) == 0:
        return float("nan")
    sr = x.mean() / x.std(ddof=1)
    skew, kurt = x.skew(), x.kurt() + 3.0  # pandas devolve excesso de curtose
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom <= 0:
        return float("nan")
    return float(_N.cdf((sr - sr_benchmark) * np.sqrt(n - 1) / np.sqrt(denom)))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Sharpe maximo esperado entre ``n_trials`` configuracoes sem edge algum (so por selecao)."""
    if n_trials <= 1:
        return 0.0
    return float(np.sqrt(sr_variance) * (
        (1 - _EULER_GAMMA) * _N.inv_cdf(1 - 1.0 / n_trials)
        + _EULER_GAMMA * _N.inv_cdf(1 - 1.0 / (n_trials * np.e))
    ))


def deflated_sharpe_ratio(pnl: pd.Series, n_trials: int, trial_srs: Sequence[float] | None = None) -> float:
    """DSR: PSR contra o melhor Sharpe que o acaso produziria em ``n_trials`` tentativas.

    ``n_trials`` e o numero de variantes/parametros/ideias testados ate chegar a este resultado
    (conte as descartadas tambem). ``trial_srs`` (Sharpe por trade de cada tentativa) estima a
    variancia entre tentativas; sem ele, assume-se 1/(n-1), a variancia do estimador sob a nula.
    Retorna a probabilidade de o edge ser real; < 0.95 = nao descarta sorte de selecao.
    """
    x = pnl.dropna()
    n = len(x)
    if n < 3:
        return float("nan")
    var = float(np.var(trial_srs, ddof=1)) if trial_srs is not None and len(trial_srs) > 1 else 1.0 / (n - 1)
    return probabilistic_sharpe_ratio(x, sr_benchmark=expected_max_sharpe(n_trials, var))


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


def block_bootstrap_mean(r: pd.Series, block: int = 20, n_sims: int = 5000, seed: int = 0) -> dict:
    """Bootstrap circular em blocos da MEDIA (preserva autocorrelacao): IC 90% e P(media <= 0)."""
    x = r.dropna().to_numpy()
    m = len(x)
    if m == 0:
        return {}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(m / block))
    starts = rng.integers(0, m, size=(n_sims, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % m
    means = x[idx.reshape(n_sims, -1)[:, :m]].mean(axis=1)
    return {"mean_p5": float(np.percentile(means, 5)), "mean_p95": float(np.percentile(means, 95)),
            "prob_le_0": float((means <= 0).mean())}


def stress_costs(run: Callable[..., tuple[pd.DataFrame, dict]], factors=(1.0, 2.0, 3.0), **kwargs) -> pd.DataFrame:
    """Reroda o backtest multiplicando slippage e taxa; o edge sobrevive a custos pessimistas?"""
    rows = []
    base_slip = kwargs.pop("slippage_ticks", 1)
    for f in factors:
        _, m = run(slippage_ticks=base_slip * f, fee_scale=f, **kwargs)
        rows.append({"custo_x": f, **m})
    return pd.DataFrame(rows)
