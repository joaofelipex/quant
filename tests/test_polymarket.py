"""Executor do Polymarket Perps (so credencial proxy) contra HTTP falso; assinatura recuperavel."""
import pytest

pytest.importorskip("eth_account")
pytest.importorskip("msgpack")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_typed_data  # noqa: E402

from quant.live import polymarket as pm  # noqa: E402
from quant.live.polymarket import PolymarketError, PolymarketPerpsExecutor  # noqa: E402

KEY = "0x" + "11" * 32
PROXY = Account.from_key(KEY).address
INST = [{"instrument_id": 7, "symbol": "ETH-USD", "quantity_decimals": 4, "price_decimals": 2, "min_notional": "10"}]


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.text = data, status, str(data)
        self.content = b"x"

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self):
        self.calls, self.portfolio, self.open_orders = [], [], []
        self.order = {"order_id": 99, "status": "filled", "filled_quantity": "0.0100"}
        self.fills = [{"order_id": 99, "price": "3641.0", "quantity": "0.0100", "fee": "0.01", "total_fee": "0.0150"}]

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split("polymarket.com")[1]
        self.calls.append((method, path, params, json, headers or {}))
        if path == "/v1/info/instruments":
            return Resp(INST)
        if path == "/v1/info/bbo":
            return Resp([{"instrument_id": 7, "bid_price": "3640.2", "ask_price": "3640.3"}])
        if path == "/v1/account/portfolio":
            return Resp({"positions": self.portfolio})
        if path == "/v1/account/open-orders":
            return Resp(self.open_orders)
        if path == "/v1/account/orders":
            return Resp([self.order])
        if path == "/v1/account/fills":
            return Resp({"data": self.fills, "more": False})
        if path == "/v1/trade/orders" and method == "POST":
            return Resp([{"status": "ok", "oid": 99}])
        if path == "/v1/trade/orders" and method == "DELETE":
            self.open_orders = []
            return Resp([{"status": "ok", "oid": 5, "ts": 1}])
        raise AssertionError((method, path))


def make(**kw):
    creds = {"proxy": PROXY, "private_key": KEY, "secret": "segredo"}
    return PolymarketPerpsExecutor("ETH-USD", creds, session=FakeHttp(), **kw)


def posts(ex):
    return [c for c in ex.http.calls if c[0] in ("POST", "DELETE")]


def test_compra_ioc_cruza_o_livro_e_devolve_preco_medio_e_taxa():
    ex = make()
    f = ex.market_order(1, 0.01, 3640.0)
    body = posts(ex)[0][3]
    row = body["op"]["args"][0]
    assert row["buy"] is True and row["tif"] == "ioc" and row["qty"] == "0.01" and "ro" not in row
    assert float(row["p"]) == pytest.approx(3640.3 * 1.01, abs=0.01) and float(row["p"]) >= 3640.3 * 1.01
    assert (f.side, f.qty, f.price, f.fee) == (1, 0.01, 3641.0, 0.015)


def test_venda_reduce_only_usa_bid_para_baixo():
    ex = make()
    ex.market_order(-1, 0.01, 3640.0, reduce_only=True)
    row = posts(ex)[0][3]["op"]["args"][0]
    assert row["buy"] is False and row["ro"] is True and float(row["p"]) <= 3640.2 * 0.99


def test_comando_e_assinado_pelo_proxy_e_recuperavel():
    ex = make()
    ex.market_order(1, 0.01, 3640.0)
    body = posts(ex)[0][3]
    assert set(body) == {"op", "sig", "salt", "ts"}
    # reconstroi o que foi assinado a partir do corpo (forma posicional) e recupera o endereco
    a = body["op"]["args"][0]
    signed = ["createOrders", [[a["iid"], a["buy"], a["p"], a["qty"], a["tif"], a["po"], a["c"]]]]
    typed = {"types": {"EIP712Domain": pm._DOMAIN, "Op": pm._OP}, "primaryType": "Op",
             "domain": {"name": "Polymarket", "version": "1", "chainId": 137},
             "message": {"data": pm.hash_op(signed), "salt": body["salt"], "ts": body["ts"]}}
    rec = Account.recover_message(encode_typed_data(full_message=typed), signature=body["sig"])
    assert rec == PROXY


def test_compactacao_remove_none_recursivamente():
    assert pm.compact(["a", [1, None, [None, 2]], None]) == ["a", [1, [2]]]
    assert pm.hash_op(["x", [1, None]]) == pm.hash_op(["x", [1]])


def test_leituras_privadas_levam_cabecalhos_do_proxy_e_publicas_nao():
    ex = make()
    ex.position()
    ex._bbo()
    priv = [c for c in ex.http.calls if c[1] == "/v1/account/portfolio"][0]
    pub = [c for c in ex.http.calls if c[1] == "/v1/info/bbo"][0]
    assert priv[4] == {"POLYMARKET-PROXY": PROXY, "POLYMARKET-SECRET": "segredo"} and pub[4] == {}


def test_posicao_long_short_e_vazia():
    ex = make()
    ex.http.portfolio = [{"instrument_id": 7, "size": "-0.5", "entry_price": "3600"}]
    p = ex.position()
    assert (p.side, p.qty, p.entry) == (-1, 0.5, 3600.0)
    ex.http.portfolio = [{"instrument_id": 7, "size": "0", "entry_price": "0"}]
    assert ex.position() is None


def test_sem_fill_e_notional_minimo_levantam_erro():
    ex = make()
    ex.http.order = {"order_id": 99, "status": "ioc_no_fill", "filled_quantity": "0"}
    with pytest.raises(PolymarketError):
        ex.market_order(1, 0.01, 3640.0)
    ex2 = make()
    with pytest.raises(PolymarketError):
        ex2.market_order(1, 0.0001, 3640.0)  # 0,0001 x 3640 < 10 de notional
    assert not posts(ex2)


def test_stop_e_tp_sl_de_posicao_a_mercado_e_cancelamento():
    ex = make()
    assert ex.has_stop() is False
    ex.place_stop(-1, 0.01, 3500.0)  # saida de venda (posicao long): stop abaixo
    body = posts(ex)[0][3]["op"]
    assert body["grp"] == "position"
    assert body["args"][0] == {"iid": 7, "buy": False, "po": False, "qty": "0", "ro": True,
                               "tr": {"tpsl": "sl", "trp": "3500", "market": True}}
    ex.http.open_orders = [{"order_id": 5, "tpsl": {"kind": "sl", "scope": "position"}}]
    assert ex.has_stop() is True
    ex.cancel_stops()
    cancel = posts(ex)[-1]
    assert cancel[0] == "DELETE" and cancel[3]["op"] == {"type": "cancelOrders", "args": [5]}
    assert ex.has_stop() is False


def test_credencial_expirada_e_recusada():
    with pytest.raises(PolymarketError):
        PolymarketPerpsExecutor("ETH-USD", {"proxy": PROXY, "private_key": KEY, "secret": "s",
                                            "expires_at": "2020-01-01T00:00:00Z"}, session=FakeHttp())


def test_instrumento_inexistente():
    with pytest.raises(PolymarketError):
        PolymarketPerpsExecutor("XYZ-USD", {"proxy": PROXY, "private_key": KEY, "secret": "s"}, session=FakeHttp())


def test_config_recusa_polymarket_fora_do_live(monkeypatch):
    from quant.live import config

    monkeypatch.setenv("QUANT_VENUE", "polymarket")
    monkeypatch.setenv("QUANT_MODE", "testnet")
    with pytest.raises(SystemExit):
        config.build_runner()
