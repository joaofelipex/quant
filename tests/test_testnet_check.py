"""A checagem da testnet precisa ser confiavel ANTES de ser apontada para uma exchange: testa-se contra falsos."""
from types import SimpleNamespace

import pytest
from test_live_robustez import StopExecutor

from quant.live.testnet_check import Check, assert_test_environment, run_checks


class CompleteFake(StopExecutor):
    """Paper com stop e taxa, como a exchange deveria se comportar."""

    def __init__(self):
        super().__init__()
        self.fee_rate = 0.0004
        self.slippage = 0.0002


def names(results, ok):
    return [c.name for c in results if c.ok is ok]


def test_executor_correto_passa_em_tudo():
    ex = CompleteFake()
    res = run_checks(ex, lambda: 100.0, qty=1.0)
    assert not names(res, False), names(res, False)
    assert ex.position() is None and ex.stops == []  # conta limpa


def test_nao_toca_em_posicao_existente():
    ex = CompleteFake()
    ex.market_order(1, 2.0, 100.0)
    res = run_checks(ex, lambda: 100.0, qty=1.0)
    assert names(res, False) == ["conta sem posicao aberta"] and len(res) == 1
    assert ex.position().qty == 2.0  # a posicao alheia continua la


def test_stop_nao_suportado_e_detectado():
    class NoStop(CompleteFake):
        def place_stop(self, *a, **k):
            return None

        def has_stop(self):
            return None

    res = run_checks(NoStop(), lambda: 100.0, qty=1.0)
    assert "stop protetor aceito (devolve id)" in names(res, False)
    assert "has_stop() enxerga o stop" in names(res, False)


def test_taxa_zero_e_fill_longe_do_ticker_sao_detectados():
    class Bad(CompleteFake):
        def __init__(self):
            super().__init__()
            self.fee_rate, self.slippage = 0.0, 0.05  # sem taxa e 5% de slippage

    res = run_checks(Bad(), lambda: 100.0, qty=1.0)
    assert {"taxa informada (> 0)", "preco do fill a menos de 1% do ticker"} <= set(names(res, False))


def test_excecao_da_exchange_vira_falha_e_ainda_limpa_a_conta():
    class Boom(CompleteFake):
        def place_stop(self, *a, **k):
            raise ConnectionError("-2021 would immediately trigger")

    ex = Boom()
    res = run_checks(ex, lambda: 100.0, qty=1.0)
    assert "execucao sem excecao" in names(res, False)
    assert ex.position() is None and ex.stops == []  # a limpeza fechou a posicao aberta


def test_emit_recebe_cada_checagem():
    visto = []
    run_checks(CompleteFake(), lambda: 100.0, qty=1.0, emit=visto.append)
    assert visto and all(isinstance(c, Check) for c in visto)


@pytest.mark.parametrize("url,ok", [
    ("https://testnet.binancefuture.com/fapi/v1", True),
    ("https://demo-fapi.binance.com/fapi/v1", True),
    ("https://fapi.binance.com/fapi/v1", False),
    ("", False),
])
def test_trava_recusa_mainnet(url, ok):
    fake = SimpleNamespace(urls={"api": {"fapiPrivate": url}})
    if ok:
        assert_test_environment(fake)
    else:
        with pytest.raises(SystemExit, match="RECUSADO"):
            assert_test_environment(fake)


def test_trava_com_ccxt_real_nos_dois_ambientes_de_teste():
    ccxt = pytest.importorskip("ccxt")
    from quant.live.executor import configure_venue

    for kind in ("testnet", "demo"):
        ex = ccxt.binanceusdm({"apiKey": "x", "secret": "y"})
        configure_venue(ex, True, kind)
        assert_test_environment(ex)  # nao levanta
    mainnet = ccxt.binanceusdm({"apiKey": "x", "secret": "y"})
    with pytest.raises(SystemExit):
        assert_test_environment(mainnet)
    with pytest.raises(ValueError):
        configure_venue(ccxt.binanceusdm(), True, "outro")
