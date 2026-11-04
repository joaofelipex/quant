import numpy as np
import pandas as pd
import pytest

from quant.validation import (
    bootstrap_trades,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    stress_costs,
    train_test_split_time,
    walk_forward_splits,
)


def test_split_temporal_sem_vazamento():
    df = pd.DataFrame({"datetime": pd.date_range("2026-01-01", periods=10, freq="D")})
    tr, te = train_test_split_time(df, "2026-01-06")
    assert tr.datetime.max() < te.datetime.min() and len(tr) + len(te) == 10


def test_walk_forward_testes_disjuntos_e_apos_o_treino():
    df = pd.DataFrame({"datetime": pd.date_range("2026-01-01", periods=400, freq="D")})
    splits = list(walk_forward_splits(df, "100D", "50D"))
    assert len(splits) == 5
    seen = set()
    for tr, te in splits:
        assert tr.datetime.max() < te.datetime.min()
        assert not seen & set(te.datetime)
        seen |= set(te.datetime)


def test_bootstrap_reprodutivel_e_limites():
    pnl = pd.Series([10, -4, 7, -3, 12, -6, 5, 8.0])
    a, b = bootstrap_trades(pnl, n_sims=500, seed=3), bootstrap_trades(pnl, n_sims=500, seed=3)
    assert a == b
    assert a["pnl_p5"] <= a["pnl_p50"] <= a["pnl_p95"]
    assert bootstrap_trades(pd.Series([1.0, 2.0, 3.0]), n_sims=200)["prob_loss"] == 0.0
    assert bootstrap_trades(pd.Series([], dtype=float)) == {}


def test_psr_no_limite():
    rng = np.random.default_rng(0)
    bom = pd.Series(rng.normal(30, 50, 200))
    ruim = pd.Series(rng.normal(-30, 50, 200))
    assert probabilistic_sharpe_ratio(bom) > 0.99
    assert probabilistic_sharpe_ratio(ruim) < 0.01
    assert np.isnan(probabilistic_sharpe_ratio(pd.Series([1.0, 1.0, 1.0])))


def test_dsr_cai_com_mais_tentativas():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(5, 100, 60))
    d1, d10, d100 = (deflated_sharpe_ratio(x, n) for n in (1, 10, 100))
    assert d1 == pytest.approx(probabilistic_sharpe_ratio(x))
    assert d1 > d10 > d100


def test_expected_max_sharpe_cresce_com_n():
    assert expected_max_sharpe(1, 0.1) == 0.0
    assert expected_max_sharpe(10, 0.1) < expected_max_sharpe(100, 0.1) < expected_max_sharpe(1000, 0.1)


def test_dsr_usa_variancia_das_tentativas():
    x = pd.Series(np.random.default_rng(2).normal(8, 100, 80))
    calmo = deflated_sharpe_ratio(x, 50, trial_srs=[0.0, 0.01, -0.01, 0.0])
    caotico = deflated_sharpe_ratio(x, 50, trial_srs=[0.0, 0.5, -0.5, 0.2])
    assert calmo > caotico


def test_stress_costs_repassa_fatores():
    chamadas = []

    def fake_run(slippage_ticks, fee_scale, **_):
        chamadas.append((slippage_ticks, fee_scale))
        return pd.DataFrame(), {"gross_pnl_brl": 100 - 10 * fee_scale}

    out = stress_costs(fake_run, factors=(1.0, 2.0, 3.0), slippage_ticks=1)
    assert chamadas == [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
    assert list(out.custo_x) == [1.0, 2.0, 3.0] and out.gross_pnl_brl.is_monotonic_decreasing
