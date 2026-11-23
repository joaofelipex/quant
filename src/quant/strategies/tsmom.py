"""Momentum de serie temporal (tendencia) diario, multi-ativo, com alvo de volatilidade.

Por ativo: sinal = media do sinal do retorno acumulado em varias janelas (``lookbacks``); tamanho = alvo de
volatilidade / volatilidade realizada (EWMA); orcamento de risco igual entre ativos; banda sem-negociacao para
cortar giro. Tudo causal: o peso decidido no fechamento do dia *t* so usa dados ate *t*
(``tests/test_tsmom.py`` trunca a serie para provar).

Execucao assumida (pessimista): o peso de *t* entra na abertura de *t+1* e rende ate a abertura de *t+2*.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trend_signal(close: pd.DataFrame, lookbacks=(20, 60, 120), long_only: bool = False) -> pd.DataFrame:
    """Media dos sinais de tendencia em [-1, 1] (ou [0, 1] se ``long_only``). NaN ate haver historico."""
    sigs = [np.sign(close / close.shift(lb) - 1) for lb in lookbacks]
    sig = sum(sigs) / len(sigs)
    return sig.clip(lower=0) if long_only else sig


def realized_vol(close: pd.DataFrame, span: int = 30, periods_per_year: int = 365) -> pd.DataFrame:
    return close.pct_change().ewm(span=span, min_periods=span).std() * np.sqrt(periods_per_year)


def target_weights(close: pd.DataFrame, lookbacks=(20, 60, 120), vol_target: float = 0.20, vol_span: int = 30,
                   long_only: bool = False, max_gross: float = 2.0) -> pd.DataFrame:
    """Pesos alvo (fracao do capital, 1 = 100%) no fechamento de cada dia; NaN vira 0."""
    sig = trend_signal(close, lookbacks, long_only)
    vol = realized_vol(close, vol_span)
    n_active = close.notna().sum(axis=1).clip(lower=1)
    w = sig * (vol_target / vol)
    w = w.div(n_active, axis=0)  # orcamento de risco igual entre ativos
    gross = w.abs().sum(axis=1)
    scale = (max_gross / gross).clip(upper=1.0).fillna(1.0)
    return w.mul(scale, axis=0).fillna(0.0)


def band_step(target: np.ndarray, cur: np.ndarray, band: float = 0.03) -> np.ndarray:
    """Um passo da banda: so move o ativo cujo alvo difere do peso atual em mais que ``band`` (ou que zerou)."""
    move = np.abs(target - cur) > band
    move |= (target == 0) & (cur != 0)  # sinal zerado fecha a posicao inteira
    return np.where(move, target, cur)


def apply_band(target: pd.DataFrame, band: float = 0.03) -> pd.DataFrame:
    """Banda sem-negociacao aplicada em sequencia sobre todo o historico (fracao do capital por ativo)."""
    t = target.to_numpy()
    out = np.zeros_like(t)
    cur = np.zeros(t.shape[1])
    for i in range(len(t)):
        cur = band_step(t[i], cur, band)
        out[i] = cur
    return pd.DataFrame(out, index=target.index, columns=target.columns)


def portfolio_returns(open_: pd.DataFrame, weights: pd.DataFrame, funding: pd.DataFrame | None = None,
                      cost_bps: float = 7.0) -> pd.DataFrame:
    """Retornos diarios liquidos. Colunas: gross, funding, cost, net, turnover.

    ``weights`` indexado pelo dia da decisao *t*; rende o retorno abertura(t+1) -> abertura(t+2), menos o funding pago
    nesse dia (long paga quando positivo) e custo proporcional ao giro.
    """
    ret = open_.shift(-2) / open_.shift(-1) - 1  # retorno da barra em que o peso de t fica exposto
    gross = (weights * ret).sum(axis=1, min_count=1)
    if funding is not None:
        f = funding.shift(-1).reindex(weights.index)  # funding do dia t+1 (mesma janela do retorno)
        fund = -(weights * f.fillna(0.0)).sum(axis=1)
    else:
        fund = pd.Series(0.0, index=weights.index)
    turnover = weights.diff().abs().fillna(weights.abs()).sum(axis=1)
    cost = -turnover * cost_bps / 1e4
    out = pd.DataFrame({"gross": gross, "funding": fund, "cost": cost, "turnover": turnover})
    out["net"] = out["gross"] + out["funding"] + out["cost"]
    return out.dropna(subset=["gross"])
