import json

import numpy as np
import pandas as pd
import pytest

from quant.live.portfolio import PortfolioPaper
from quant.strategies import tsmom

SYMS = ["A", "B", "C"]


def _panel(n=330, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.001, 0.03, (n, 3)), axis=0)), index=idx, columns=SYMS)
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + rng.normal(0, 0.002, (n, 3)))
    funding = pd.DataFrame(rng.normal(0.0003, 0.0002, (n, 3)), index=idx, columns=SYMS)
    return open_, close, funding


def _bot(tmp_path):
    return PortfolioPaper(SYMS, tmp_path / "s.json", tmp_path / "log.csv")


def _start_state(tmp_path, first_day):
    (tmp_path / "s.json").write_text(json.dumps(
        {"last_date": str(first_day)[:10], "equity": 1.0, "weights": {s: 0.0 for s in SYMS}}))


def test_paper_reproduz_o_backtest_do_estudo(tmp_path):
    """Mesma mecanica: soma do PnL e dos custos do paper == soma do portfolio_returns do estudo."""
    open_, close, funding = _panel()
    _start_state(tmp_path, open_.index[0])
    bot = _bot(tmp_path)
    rows = bot.run(open_, close, funding, open_.index[-1])
    paper = pd.DataFrame(rows)

    w = tsmom.apply_band(tsmom.target_weights(close))
    study = tsmom.portfolio_returns(open_, w, funding, cost_bps=7.0)
    last = open_.index[-1]
    assert paper["pnl"].sum() == pytest.approx(study.loc[: last - pd.Timedelta(days=2), "gross"].sum())
    assert paper["funding"].sum() == pytest.approx(study.loc[: last - pd.Timedelta(days=2), "funding"].sum())
    # o estudo descarta os 2 ultimos dias (sem retorno futuro); o custo de entrada do paper em D e o do estudo em D-1
    assert paper["cost"].iloc[:-1].sum() == pytest.approx(study.loc[: last - pd.Timedelta(days=2), "cost"].sum())
    assert paper["turnover"].sum() > 0  # o teste so vale se a estrategia de fato negociou


def test_idempotente_e_recupera_dias_perdidos(tmp_path):
    open_, close, funding = _panel()
    d_mid, d_end = open_.index[250], open_.index[-1]

    a = tmp_path / "a"
    a.mkdir()
    _start_state(a, open_.index[0])
    full = _bot(a)
    full.run(open_, close, funding, d_end)

    b = tmp_path / "b"
    b.mkdir()
    _start_state(b, open_.index[0])
    gap = _bot(b)
    gap.run(open_, close, funding, d_mid)  # servico "cai" depois de d_mid
    assert gap.run(open_, close, funding, d_mid) == []  # rodar de novo no mesmo dia nao faz nada
    gap.run(open_, close, funding, d_end)  # volta e repoe os dias perdidos

    sa, sb = (json.loads((x / "s.json").read_text()) for x in (a, b))
    assert sa["last_date"] == sb["last_date"]
    assert sa["equity"] == pytest.approx(sb["equity"])
    assert sa["weights"] == pytest.approx(sb["weights"])


def test_sem_dados_do_dia_para(tmp_path):
    open_, close, funding = _panel(n=300)
    _start_state(tmp_path, open_.index[-2])
    bot = _bot(tmp_path)
    future = open_.index[-1] + pd.Timedelta(days=5)
    rows = bot.run(open_, close, funding, future)
    assert len(rows) == 1 and bot.load(future)["last_date"] == str(open_.index[-1])[:10]


def test_notifica_o_rebalanceamento(tmp_path):
    open_, close, funding = _panel()
    msgs = []
    bot = PortfolioPaper(SYMS, tmp_path / "s.json", tmp_path / "log.csv", notify=msgs.append)
    _start_state(tmp_path, open_.index[0])
    bot.run(open_, close, funding, open_.index[-1])
    assert msgs and "rebalanceamento" in msgs[0]
