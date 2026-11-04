import numpy as np
import pandas as pd
import pytest

from quant.metrics import calmar, max_drawdown, sharpe, sortino, trade_metrics


def test_max_drawdown():
    assert max_drawdown(pd.Series([10, -5, -5, 20, -3])) == -10


def test_trade_metrics_conta_de_cabeca():
    m = trade_metrics(pd.Series([10.0, -5.0, 10.0, -5.0]))
    assert m["n_trades"] == 4
    assert m["win_rate"] == 0.5
    assert m["profit_factor"] == pytest.approx(2.0)
    assert m["expectancy"] == pytest.approx(2.5)
    assert m["max_drawdown"] == pytest.approx(-5.0)


def test_trade_metrics_vazio_e_sem_perdas():
    assert trade_metrics(pd.Series([], dtype=float)) == {"n_trades": 0}
    assert trade_metrics(pd.Series([1.0, 2.0]))["profit_factor"] == float("inf")


def test_sharpe_sortino_calmar():
    r = pd.Series([0.01, -0.005, 0.02, 0.0, 0.015])
    assert sharpe(r) == pytest.approx(r.mean() / r.std(ddof=1) * np.sqrt(252))
    dd = np.sqrt(((np.minimum(r, 0)) ** 2).mean())  # so 1 retorno negativo: std dos negativos seria NaN
    assert sortino(r) == pytest.approx(r.mean() / dd * np.sqrt(252))
    assert calmar(r) > 0
    assert sharpe(pd.Series([0.01] * 5)) == 0.0  # volatilidade zero nao explode
