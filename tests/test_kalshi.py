"""Executor da Kalshi contra uma sessao HTTP falsa: conversoes, ordem IOC, stop como exit trigger, assinatura."""
import base64

import pytest

from quant.live import kalshi
from quant.live.kalshi import KalshiError, KalshiPerpsExecutor

REAL_SIGN = kalshi.sign  # o fixture autouse troca 'sign' nos outros testes

MARKET = {"ticker": "KXETHPERP1", "status": "active", "contract_size": "0.001000", "underlying_multiplier": "1.000000",
          "tick_size": "0.0001", "minimum_quantity": "1.00", "fractional_trading_enabled": False, "market_version": 1,
          "bid": "1.7140", "ask": "1.7175", "price": "1.7160"}


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.text = data, status, str(data)
        self.content = b"x" if data is not None else b""

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self):
        self.calls, self.fill, self.positions, self.triggers = [], 10.0, [], []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split("/trade-api/v2")[1]
        self.calls.append((method, path, params, json, headers))
        if path.startswith("/margin/markets/"):
            return Resp({"market": MARKET})
        if path == "/margin/orders" and method == "POST":
            return Resp({"order_id": "o1", "fill_count": f"{self.fill:.2f}", "remaining_count": "0.00",
                         "average_fill_price": "1.7175", "average_fee_paid": "0.0010"})
        if path == "/margin/positions":
            return Resp({"positions": self.positions})
        if path.endswith("/exit_trigger"):
            if method == "PUT":
                self.triggers = [{"id": "t1", "status": "active", "stop_loss_price": json["stop_loss_price"]}]
                return Resp(self.triggers[0])
            if method == "DELETE":
                self.triggers = []
                return Resp(None)
            return Resp({"exit_triggers": self.triggers})
        raise AssertionError(path)


@pytest.fixture
def ex():
    return KalshiPerpsExecutor("KXETHPERP1", "kid", None, env="demo", session=FakeHttp(), rebase=False)


@pytest.fixture(autouse=True)
def no_signing(monkeypatch):
    monkeypatch.setattr(kalshi, "sign", lambda *a: "assinatura")


def orders(ex):
    return [c for c in ex.http.calls if c[1] == "/margin/orders"]


def test_compra_vira_ioc_cruzando_o_livro_e_converte_unidades(ex):
    f = ex.market_order(1, 0.01, 1717.5)  # 0,01 ETH = 10 contratos de 0,001
    body = orders(ex)[0][3]
    assert body["side"] == "bid" and body["count"] == "10.00" and body["time_in_force"] == "immediate_or_cancel"
    assert float(body["price"]) == pytest.approx(1.7175 * 1.01, abs=1e-4) and float(body["price"]) >= 1.7175 * 1.01
    assert f.side == 1 and f.qty == pytest.approx(0.01) and f.price == pytest.approx(1717.5)  # 1,7175 / 0,001
    assert f.fee == pytest.approx(0.0010 * 10)


def test_venda_usa_o_bid_e_arredonda_para_baixo(ex):
    ex.market_order(-1, 0.01, 1714.0)
    body = orders(ex)[0][3]
    assert body["side"] == "ask" and float(body["price"]) <= 1.7140 * 0.99


def test_reduce_only_e_repassado(ex):
    ex.market_order(-1, 0.01, 1714.0, reduce_only=True)
    assert orders(ex)[0][3]["reduce_only"] is True


def test_sem_fill_levanta_erro(ex):
    ex.http.fill = 0.0
    with pytest.raises(KalshiError):
        ex.market_order(1, 0.01, 1717.5)


def test_quantidade_abaixo_do_minimo_nao_envia_ordem(ex):
    with pytest.raises(KalshiError):
        ex.market_order(1, 0.0001, 1717.5)
    assert not orders(ex)


def test_mercado_inativo_nao_envia_ordem(ex, monkeypatch):
    monkeypatch.setitem(MARKET, "status", "halted")
    with pytest.raises(KalshiError):
        ex.market_order(1, 0.01, 1717.5)
    monkeypatch.setitem(MARKET, "status", "active")


def test_posicao_long_e_short_em_unidades_do_ativo(ex):
    ex.http.positions = [{"market_ticker": "KXETHPERP1", "position": "-25.00", "entry_price": "1.7200"}]
    p = ex.position()
    assert p.side == -1 and p.qty == pytest.approx(0.025) and p.entry == pytest.approx(1720.0)
    ex.http.positions = [{"market_ticker": "KXETHPERP1", "position": "0.00", "entry_price": "0"}]
    assert ex.position() is None


def test_stop_e_exit_trigger_e_has_stop_enxerga(ex):
    assert ex.has_stop() is False
    ex.place_stop(-1, 0.01, 1700.0)
    put = [c for c in ex.http.calls if c[0] == "PUT"][0]
    assert put[1] == "/margin/cross/positions/KXETHPERP1/exit_trigger" and put[3] == {"stop_loss_price": "1.7000"}
    assert ex.has_stop() is True
    ex.cancel_stops()
    assert ex.has_stop() is False


def test_rebase_no_demo_normaliza_o_preco_para_o_do_feed():
    ex = KalshiPerpsExecutor("KXETHPERP1", "kid", None, env="demo", session=FakeHttp())  # rebase padrao no demo
    f = ex.market_order(1, 0.01, 3000.0)  # feed diz 3000, o demo cota ~1716
    assert f.price == pytest.approx(3000 * (1.7175 / 1.7160), rel=1e-3)
    assert ex.basis == pytest.approx(1716.0 / 3000.0)
    ex.place_stop(-1, 0.01, 2900.0)  # stop no preco do feed vira o preco do demo
    put = [c for c in ex.http.calls if c[0] == "PUT"][0]
    assert float(put[3]["stop_loss_price"]) == pytest.approx(2900 * ex.basis * 0.001, abs=1e-4)
    ex2 = KalshiPerpsExecutor("KXETHPERP1", "kid", None, env="demo", session=FakeHttp())
    ex2.import_state(ex.export_state())
    assert ex2.basis == ex.basis


def test_assinatura_rsa_pss_e_ed25519_verificaveis():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

    msg = b"1700000000000GET/trade-api/v2/margin/positions"
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = base64.b64decode(REAL_SIGN(rsa_key, "1700000000000", "GET", "/trade-api/v2/margin/positions?ticker=X"))
    rsa_key.public_key().verify(sig, msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                      salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    ed = ed25519.Ed25519PrivateKey.generate()
    sig_ed = base64.b64decode(REAL_SIGN(ed, "1700000000000", "GET", "/trade-api/v2/margin/positions"))
    ed.public_key().verify(sig_ed, msg)


def test_env_e_modo_invalidos():
    with pytest.raises(ValueError):
        KalshiPerpsExecutor("X", "k", None, env="outro", session=FakeHttp())
    with pytest.raises(ValueError):
        KalshiPerpsExecutor("KXETHPERP1", "k", None, margin_mode="x", session=FakeHttp())


def _recusa(ex, code, status=400):
    import json as _json

    http = ex.http
    original = http.request

    def request(method, url, **kw):
        if method == "PUT" and url.endswith("/exit_trigger"):
            r = Resp({"error": {"code": code, "message": "x"}}, status)
            r.text = _json.dumps(r.data)
            return r
        return original(method, url, **kw)

    http.request = request


@pytest.mark.parametrize("code", ["stop_loss_past_liquidation", "stop_loss_already_breached",
                                  "take_profit_already_breached", "close_order_blocks_exit_trigger"])
def test_stop_recusado_vira_stoprejected_com_o_codigo(ex, code):
    _recusa(ex, code)
    with pytest.raises(kalshi.StopRejected) as e:
        ex.place_stop(-1, 0.01, 1700.0)
    assert e.value.code == code and "stop recusado" in str(e.value)


def test_outro_erro_no_stop_continua_kalshierror_simples(ex):
    _recusa(ex, "internal_error", 500)
    with pytest.raises(KalshiError) as e:
        ex.place_stop(-1, 0.01, 1700.0)
    assert not isinstance(e.value, kalshi.StopRejected) and e.value.code == "internal_error"


def test_trigger_cancelado_nao_conta_como_stop(ex):
    ex.http.triggers = [{"id": "t9", "status": "canceled", "stop_loss_price": "1.7000"}]
    assert ex.has_stop() is False
