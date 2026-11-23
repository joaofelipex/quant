"""Carry de funding delta-neutro: comprado no spot + vendido no perpetuo, na mesma quantidade.

Quem esta vendido no perpetuo RECEBE o funding quando ele e positivo (long paga short). O hedge cancela o
risco direcional; sobram tres coisas: o funding (a receita), a variacao da base spot-perp (ruido, media ~0) e
o custo de abrir/fechar as duas pernas. Nao ha almoco gratis: o risco esta na cauda (funding negativo
prolongado, liquidacao da perna vendida numa alta violenta, contraparte), nao na volatilidade diaria.

Tudo causal: a posicao do dia *t* so usa funding ate o dia *t-1* (``tests/test_funding_carry.py`` trunca a serie).

Convencoes (pessimistas): posicao do dia *t* vai da abertura de *t* a abertura de *t+1*; funding do dia *t* e a
soma das liquidacoes de 00:00, 08:00 e 16:00 UTC; margem do perpetuo (``margin``, fracao do nocional) e capital
parado que rende zero, assim como o caixa fora de posicao; a margem e recomposta todo dia sem custo
(transferencia interna), entao so a alta INTRADIARIA ameaca liquidar.
"""
from __future__ import annotations

import pandas as pd

DAYS_PER_YEAR = 365


def daily_funding(funding: pd.DataFrame) -> pd.Series:
    """Soma o funding (por periodo de 8 h) por dia UTC. ``funding``: colunas ``datetime`` e ``funding_rate``."""
    day = pd.to_datetime(funding["datetime"]).dt.tz_localize(None).dt.normalize()
    return funding.groupby(day)["funding_rate"].sum().sort_index()


def carry_signal(funding_daily: pd.DataFrame, lookback: int = 14, hurdle_ann: float = 0.05) -> pd.DataFrame:
    """True no dia *t* se o funding medio dos ``lookback`` dias ate *t-1*, anualizado, supera ``hurdle_ann``."""
    trailing = funding_daily.rolling(lookback, min_periods=lookback).mean() * DAYS_PER_YEAR
    return (trailing > hurdle_ann).shift(1, fill_value=False)  # shift: decide com dados de ontem


def carry_returns(spot_open: pd.DataFrame, perp_open: pd.DataFrame, funding_daily: pd.DataFrame, on: pd.DataFrame,
                  switch_cost_bps: float = 20.0, margin: float = 0.20) -> dict[str, pd.DataFrame]:
    """Retornos diarios SOBRE O CAPITAL, por ativo: ``funding``, ``basis``, ``cost`` e ``net``.

    Capital por ativo = nocional x (1 + margin). ``switch_cost_bps`` = custo de UMA troca de estado (abrir ou fechar as
    duas pernas: taxas + slippage), sobre o nocional.
    """
    idx = spot_open.index
    on = on.reindex(idx, fill_value=False).astype(bool)
    hedge = (spot_open.shift(-1) / spot_open - 1) - (perp_open.shift(-1) / perp_open - 1)  # ruido da base
    fund = funding_daily.reindex(idx).fillna(0.0)
    flag = on.astype(float)
    switches = flag.diff().abs()
    switches.iloc[0] = flag.iloc[0]  # estar ligado no 1o dia ja custou a abertura
    scale = 1.0 / (1.0 + margin)
    out = {
        "funding": flag * fund * scale,
        "basis": flag * hedge * scale,
        "cost": -switches * switch_cost_bps / 1e4 * scale,
    }
    out["net"] = out["funding"] + out["basis"].fillna(0.0) + out["cost"]
    last = idx[-1]  # o ultimo dia nao tem abertura seguinte: sem retorno de hedge definido
    return {k: v.drop(index=last) for k, v in out.items()}


def portfolio(per_asset: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Capital dividido em partes iguais entre os ativos; a parte de quem esta desligado fica parada (rende zero)."""
    return pd.DataFrame({k: v.mean(axis=1) for k, v in per_asset.items()})


def liquidation_days(perp_open: pd.DataFrame, perp_high: pd.DataFrame, on: pd.DataFrame, margin: float = 0.20,
                     maintenance: float = 0.005) -> pd.DataFrame:
    """Dias em que a perna vendida estaria ligada e a maxima do dia superou a abertura em mais que a margem livre."""
    spike = perp_high / perp_open - 1
    return (spike >= margin - maintenance) & on.reindex(perp_open.index, fill_value=False).astype(bool)
