import numpy as np
import pandas as pd
import pytest

from quant.strategies import funding_carry as fc

DAYS = pd.date_range("2024-01-01", periods=200, freq="D")


def frame(values, cols=("A",)):
    return pd.DataFrame({c: values for c in cols}, index=DAYS[: len(values)], dtype=float)


def test_daily_funding_soma_as_tres_liquidacoes_do_dia_utc():
    f = pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00", "2024-01-02 00:00"],
                                   utc=True),
        "funding_rate": [0.0001, 0.0002, 0.0003, -0.0001],
    })
    d = fc.daily_funding(f)
    assert d.tolist() == pytest.approx([0.0006, -0.0001]) and d.index[0] == pd.Timestamp("2024-01-01")


def test_sinal_usa_so_dados_de_ontem():
    # funding alto a partir do indice 2; com lookback 3 e piso de 15% a.a. a media so passa quando os 3 dias sao altos
    # (indice 4) => a posicao so liga no dia seguinte (indice 5)
    f = frame([0, 0, 0.0005, 0.0005, 0.0005, 0.0005])
    on = fc.carry_signal(f, lookback=3, hurdle_ann=0.15)
    assert on["A"].tolist() == [False, False, False, False, False, True]


def test_sinal_nao_depende_do_futuro():
    rng = np.random.default_rng(0)
    f = frame(rng.normal(0.0002, 0.0003, 120))
    full = fc.carry_signal(f, lookback=7, hurdle_ann=0.05)
    for cut in (30, 60, 90):
        part = fc.carry_signal(f.iloc[:cut], lookback=7, hurdle_ann=0.05)
        pd.testing.assert_frame_equal(full.iloc[:cut], part)


def test_retorno_so_de_funding_com_custo_na_abertura():
    flat = frame([100] * 6)
    fund = frame([0.0003] * 6)
    on = frame([1] * 6).astype(bool)
    r = fc.carry_returns(flat, flat, fund, on, switch_cost_bps=20, margin=0.25)
    assert len(r["net"]) == 5  # o ultimo dia nao tem abertura seguinte
    assert r["net"]["A"].iloc[0] == pytest.approx((0.0003 - 0.0020) / 1.25)  # funding menos abertura, sobre o capital
    assert r["net"]["A"].iloc[1:].tolist() == pytest.approx([0.0003 / 1.25] * 4)
    assert r["basis"]["A"].abs().sum() == 0


def test_base_spot_menos_perp_entra_no_retorno():
    spot = frame([100, 101, 101, 101, 101, 101])
    perp = frame([100, 100.9, 100.9, 100.9, 100.9, 100.9])
    on = frame([1] * 6).astype(bool)
    r = fc.carry_returns(spot, perp, frame([0] * 6), on, switch_cost_bps=0, margin=0.0)
    assert r["basis"]["A"].iloc[0] == pytest.approx(0.01 - 0.009)  # spot subiu 1%, perp 0,9%
    assert r["net"]["A"].iloc[1:].abs().max() < 1e-12


def test_fora_de_posicao_nao_recebe_nem_paga_e_cada_troca_custa_uma_vez():
    flat = frame([100] * 6)
    fund = frame([0.001] * 6)
    on = pd.DataFrame({"A": [True, True, False, False, True, True]}, index=DAYS[:6])
    r = fc.carry_returns(flat, flat, fund, on, switch_cost_bps=10, margin=0.0)
    custo = r["cost"]["A"].tolist()
    assert custo == pytest.approx([-0.001, 0.0, -0.001, 0.0, -0.001])  # abre, fecha, reabre
    assert r["funding"]["A"].tolist() == pytest.approx([0.001, 0.001, 0.0, 0.0, 0.001])


def test_funding_negativo_com_posicao_ligada_e_prejuizo():
    flat = frame([100] * 4)
    r = fc.carry_returns(flat, flat, frame([-0.0004] * 4), frame([1] * 4).astype(bool), switch_cost_bps=0, margin=0.0)
    assert (r["net"]["A"] < 0).all()


def test_portfolio_divide_o_capital_e_o_desligado_fica_parado():
    flat = frame([100] * 4, cols=("A", "B"))
    on = pd.DataFrame({"A": [True] * 4, "B": [False] * 4}, index=DAYS[:4])
    fund = frame([0.001] * 4, cols=("A", "B"))
    r = fc.carry_returns(flat, flat, fund, on, switch_cost_bps=0, margin=0.0)
    p = fc.portfolio(r)
    assert p["net"].tolist() == pytest.approx([0.0005] * 3)  # metade do capital rende 0,1%/dia; a outra fica parada


def test_liquidacao_so_conta_com_a_perna_ligada():
    op = frame([100] * 3)
    hi = frame([125, 105, 125])  # +25% no dia 0 e no dia 2
    on = pd.DataFrame({"A": [True, True, False]}, index=DAYS[:3])
    liq = fc.liquidation_days(op, hi, on, margin=0.20)
    assert liq["A"].tolist() == [True, False, False]
