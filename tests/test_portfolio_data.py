"""Fonte de dados do paper: endpoint publico de mercado (sem chave) e funding opcional, sem inventar zeros."""
import json
import logging
import urllib.error

import numpy as np
import pandas as pd
import pytest
from test_portfolio_paper import _bot, _panel, _start_state

from quant import dashboard
from quant.live import portfolio as pf

DAY_MS = 86_400_000
T0_MS = int(pd.Timestamp("2026-03-01", tz="UTC").timestamp() * 1000)


def klines(n=3, base=100.0):
    """[open_time, open, high, low, close, ...] como a API devolve (precos em texto)."""
    return [[T0_MS + i * DAY_MS, str(base + i), str(base + i + 2), str(base + i - 1), str(base + i + 1), "10.0"]
            for i in range(n)]


def http_error(code):
    return urllib.error.HTTPError("https://x", code, "msg", None, None)


# ---- precos ----------------------------------------------------------------------------------------------------
def test_fetch_daily_usa_o_endpoint_publico_de_dados_e_le_os_klines(monkeypatch):
    urls = []

    def fake(url, **_):
        urls.append(url)
        return klines(3, base=100.0 if "BTC" in url else 200.0)

    monkeypatch.setattr(pf, "get_json", fake)
    opens, closes = pf.fetch_daily(["BTCUSDT", "ETHUSDT"], limit=3)
    assert all(u.startswith("https://data-api.binance.vision/api/v3/klines?") for u in urls)
    assert all("interval=1d" in u and "limit=3" in u for u in urls)
    assert list(opens.columns) == ["BTCUSDT", "ETHUSDT"]
    assert opens.index[0] == pd.Timestamp("2026-03-01") and opens.index.is_monotonic_increasing
    assert opens["BTCUSDT"].tolist() == [100.0, 101.0, 102.0] and closes["ETHUSDT"].tolist() == [201.0, 202.0, 203.0]


def test_a_fonte_padrao_nao_e_a_api_bloqueada_por_regiao():
    assert pf.DATA_BASE == "https://data-api.binance.vision"
    assert "api.binance.com" not in pf.DATA_BASE.replace("data-api.binance.vision", "")


def test_get_json_repete_429_mas_nao_repete_451(monkeypatch):
    chamadas = {"n": 0}

    class Resp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.body

    def urlopen_429_depois_ok(req, timeout):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise http_error(429)
        return Resp(json.dumps([1, 2]).encode())

    monkeypatch.setattr(pf.time, "sleep", lambda s: None)
    monkeypatch.setattr(pf.urllib.request, "urlopen", urlopen_429_depois_ok)
    assert pf.get_json("https://x") == [1, 2] and chamadas["n"] == 2

    chamadas["n"] = 0

    def urlopen_451(req, timeout):
        chamadas["n"] += 1
        raise http_error(451)

    monkeypatch.setattr(pf.urllib.request, "urlopen", urlopen_451)
    with pytest.raises(urllib.error.HTTPError):
        pf.get_json("https://x")
    assert chamadas["n"] == 1  # bloqueio regional e definitivo: nao insiste


# ---- funding ---------------------------------------------------------------------------------------------------
def test_funding_451_devolve_vazio_loga_uma_vez_e_nao_insiste(monkeypatch, caplog):
    chamadas = []

    def fake(url, **_):
        chamadas.append(url)
        raise http_error(451)

    monkeypatch.setattr(pf, "get_json", fake)
    with caplog.at_level(logging.WARNING, logger="quant.live"):
        out = pf.fetch_funding(["BTCUSDT", "ETHUSDT", "BNBUSDT"], pd.Timestamp("2026-03-01"))
    assert out.empty and len(chamadas) == 1  # parou no primeiro 451
    assert sum("funding indisponivel" in m for m in caplog.messages) == 1


def test_funding_soma_por_dia_utc(monkeypatch):
    rows = [{"fundingTime": T0_MS + h * 3_600_000, "fundingRate": "0.0001"} for h in (0, 8, 16, 24)]
    monkeypatch.setattr(pf, "get_json", lambda url, **_: rows)
    out = pf.fetch_funding(["BTCUSDT"], pd.Timestamp("2026-03-01"))
    assert out["BTCUSDT"].tolist() == pytest.approx([0.0003, 0.0001])


# ---- paper sem funding -----------------------------------------------------------------------------------------
def test_sem_funding_o_log_marca_nan_e_o_equity_ignora_o_funding(tmp_path):
    open_, close, funding = _panel()
    com, sem = tmp_path / "com", tmp_path / "sem"
    for d in (com, sem):
        d.mkdir()
        _start_state(d, open_.index[0])
    rows_zero = _bot(com).run(open_, close, funding * 0.0, open_.index[-1])  # funding conhecido e igual a zero
    rows_sem = _bot(sem).run(open_, close, pd.DataFrame(), open_.index[-1])  # funding indisponivel

    f = pd.Series([r["funding"] for r in rows_sem])
    assert f.isna().any() and (f.dropna() == 0).all()  # NaN so onde havia posicao; nunca um numero inventado
    assert (pd.Series([r["funding"] for r in rows_zero]) == 0).all()
    e0, e1 = json.loads((com / "s.json").read_text())["equity"], json.loads((sem / "s.json").read_text())["equity"]
    assert e1 == pytest.approx(e0)  # indisponivel = ignorado no equity, igual a zero
    assert rows_sem[0]["funding"] == 0.0  # o 1o dia ainda nao tinha posicao: funding conhecido (zero), nao NaN


def test_funding_conhecido_nao_vira_nan(tmp_path):
    open_, close, funding = _panel()
    _start_state(tmp_path, open_.index[0])
    rows = _bot(tmp_path).run(open_, close, funding, open_.index[-1])
    assert not np.isnan([r["funding"] for r in rows]).any()


# ---- painel ----------------------------------------------------------------------------------------------------
def _log(funding):
    return pd.DataFrame({"date": pd.date_range("2026-11-23", periods=3), "equity": [1.0, 1.001, 1.002],
                         "pnl": [0.0, 0.001, 0.001], "funding": funding, "cost": [0.0, 0.0, 0.0],
                         "turnover": [0.0, 0.0, 0.0], "gross": [0.3, 0.3, 0.3]})


def test_painel_avisa_quando_ha_dias_sem_funding(tmp_path):
    state = {"weights": {"BTCUSDT": 0.03}}
    page = dashboard.build_html(state, _log([0.0, np.nan, np.nan]), tmp_path / "x.md")
    assert "Funding indisponivel em 2 dia(s)" in page
    ok = dashboard.build_html(state, _log([0.0, -0.0001, -0.0001]), tmp_path / "x.md")
    assert "Funding indisponivel" not in ok


def test_log_csv_com_nan_volta_como_nan(tmp_path):
    p = tmp_path / "log.csv"
    _log([0.0, np.nan, np.nan]).to_csv(p, index=False)
    back = dashboard.read_log(p)
    assert back["funding"].isna().sum() == 2

