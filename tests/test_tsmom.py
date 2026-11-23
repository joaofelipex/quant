import numpy as np
import pandas as pd
import pytest

from quant.strategies import tsmom


def _prices(n=400, k=3, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, (n, k)), axis=0)), index=idx,
                         columns=list("ABC")[:k])
    return close


def test_pesos_sao_causais():
    """O peso do dia t nao muda se apagarmos todo o futuro."""
    close = _prices()
    full = tsmom.target_weights(close)
    for t in (150, 250, 399):
        cut = tsmom.target_weights(close.iloc[: t + 1])
        pd.testing.assert_series_equal(full.iloc[t], cut.iloc[t], check_names=False)


def test_banda_tambem_e_causal():
    close = _prices()
    full = tsmom.apply_band(tsmom.target_weights(close))
    cut = tsmom.apply_band(tsmom.target_weights(close.iloc[:300]))
    pd.testing.assert_series_equal(full.iloc[299], cut.iloc[299], check_names=False)


def test_long_only_nao_tem_peso_negativo_e_limite_de_alavancagem():
    close = _prices()
    w = tsmom.target_weights(close, long_only=True, max_gross=1.0)
    assert (w >= 0).all().all()
    assert (w.abs().sum(axis=1) <= 1.0 + 1e-9).all()


def test_alvo_de_vol_reduz_peso_quando_vol_sobe():
    idx = pd.date_range("2022-01-01", periods=300, freq="D")
    calm = pd.Series(100 * np.exp(np.arange(300) * 0.002), index=idx)
    rng = np.random.default_rng(0)
    wild = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.08, 300))), index=idx)
    w = tsmom.target_weights(pd.DataFrame({"calm": calm, "wild": wild}), long_only=True)
    assert w["calm"].iloc[-1] > w["wild"].iloc[-1]


def test_retorno_da_barra_seguinte_e_giro_com_custo():
    idx = pd.date_range("2022-01-01", periods=6, freq="D")
    open_ = pd.DataFrame({"A": [100.0, 100, 110, 121, 121, 121]}, index=idx)
    w = pd.DataFrame({"A": [0.0, 1.0, 1.0, 0.0, 0.0, 0.0]}, index=idx)
    r = tsmom.portfolio_returns(open_, w, cost_bps=10.0)
    # peso de d1 (=1): abre em open[d2]=110, rende ate open[d3]=121 => +10%; giro 1 em d1 => custo 10 bps
    assert r.loc[idx[1], "gross"] == pytest.approx(121 / 110 - 1)
    assert r.loc[idx[1], "cost"] == pytest.approx(-0.001)
    assert r.loc[idx[3], "cost"] == pytest.approx(-0.001)  # fechar a posicao tambem custa


def test_funding_positivo_custa_para_quem_esta_comprado():
    idx = pd.date_range("2022-01-01", periods=5, freq="D")
    open_ = pd.DataFrame({"A": [100.0] * 5}, index=idx)
    w = pd.DataFrame({"A": [1.0] * 5}, index=idx)
    f = pd.DataFrame({"A": [0.001] * 5}, index=idx)
    r = tsmom.portfolio_returns(open_, w, funding=f, cost_bps=0.0)
    assert r["funding"].iloc[0] == pytest.approx(-0.001)
