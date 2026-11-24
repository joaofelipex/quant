"""Executor dos perps do Polymarket pela API HTTP, so com a credencial PROXY (nunca a chave da carteira dona da conta).

    https://docs.polymarket.com/perps  ·  base: https://api.perpetuals.polymarket.com

NAO TESTADO contra a exchange: a assinatura foi reimplementada a partir do codigo do SDK oficial (``polymarket-client``,
lido, nao executado) e o formato das respostas vem do OpenAPI. Valide com posicao minima antes de qualquer coisa.

* Credencial: proxy (endereco + chave privada + segredo), gerada UMA vez por voce com a carteira da conta (veja
  ``deploy/polymarket-proxy.py``) e guardada em arquivo JSON modo 600. Expira (padrao 1 semana): renove antes.
* Leituras privadas levam os cabecalhos ``POLYMARKET-PROXY``/``POLYMARKET-SECRET``; comandos (ordem, cancelamento) levam
  no corpo ``op`` + ``sig`` (EIP-712 ``Op`` assinado pela chave do proxy) + ``salt`` + ``ts``.
* **Geografia:** o Polymarket proibe ordens a partir dos EUA e de outras jurisdicoes. Rode so de uma maquina fora delas;
  este codigo NAO tenta verificar nem contornar isso.
* Ordem a mercado = limite IOC cruzando o livro (teto de 1%, dentro do ``price_bounds``). Stop protetor = TP/SL de
  *posicao* (a mercado, fecha a posicao inteira quando o mark toca o gatilho).
"""
from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

from .executor import Executor
from .models import Fill, Position

log = logging.getLogger("quant.live")

BASE = "https://api.perpetuals.polymarket.com"
CHAIN_ID = 137
_DOMAIN = [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
           {"name": "chainId", "type": "uint256"}]
_OP = [{"name": "data", "type": "bytes32"}, {"name": "salt", "type": "uint64"}, {"name": "ts", "type": "uint64"}]
TERMINAL = {"filled", "ioc_no_fill", "ioc_expired", "stp_cancelled", "cancelled", "canceled", "rejected", "expired"}


class PolymarketError(RuntimeError):
    pass


# ---- assinatura (reimplementa o signing.py do SDK oficial) ----------------------------------------------
def compact(value):
    """Remove entradas ``None`` das listas, recursivamente: o servidor assina a forma compacta."""
    if isinstance(value, (list, tuple)):
        return [compact(v) for v in value if v is not None]
    return value


def hash_op(op) -> str:
    import msgpack
    from eth_utils.crypto import keccak

    return "0x" + keccak(msgpack.packb(compact(op))).hex()


def sign_op(private_key: str, op, *, salt: int, ts: int, chain_id: int = CHAIN_ID) -> str:
    from eth_account import Account

    payload = {"types": {"EIP712Domain": _DOMAIN, "Op": _OP}, "primaryType": "Op",
               "domain": {"name": "Polymarket", "version": "1", "chainId": chain_id},
               "message": {"data": hash_op(op), "salt": salt, "ts": ts}}
    return "0x" + bytes(Account.from_key(private_key).sign_typed_data(full_message=payload).signature).hex()


def load_credentials(path: str | Path) -> dict:
    c = json.loads(Path(path).read_text())
    for k in ("proxy", "private_key", "secret"):
        if not c.get(k):
            raise PolymarketError(f"credencial sem '{k}' em {path}")
    return c


def _d(x) -> Decimal:
    return Decimal(str(x))


def _fmt(x: Decimal) -> str:
    return format(x.normalize(), "f") if x != 0 else "0"


class PolymarketPerpsExecutor(Executor):
    SLIPPAGE = Decimal("0.01")   # teto do limite IOC em relacao ao melhor preco (o book aceita ate price_bounds=2%)
    SETTLE_TRIES = 6
    SETTLE_DELAY_S = 0.5
    EXPIRY_WARN_S = 24 * 3600

    def __init__(self, symbol: str, credentials: dict, *, base: str = BASE, session=None, sign=sign_op,
                 chain_id: int = CHAIN_ID):
        if session is None:
            import requests

            session = requests.Session()
        self.http, self.base, self.sign, self.chain_id = session, base.rstrip("/"), sign, chain_id
        self.proxy, self.key, self.secret = credentials["proxy"], credentials["private_key"], credentials["secret"]
        self._check_expiry(credentials.get("expires_at"))
        inst = next((i for i in self._get("/v1/info/instruments", auth=False) if i["symbol"] == symbol), None)
        if inst is None:
            raise PolymarketError(f"instrumento {symbol!r} nao encontrado")
        self.symbol, self.iid = symbol, int(inst["instrument_id"])
        self.qty_dec, self.px_dec = int(inst["quantity_decimals"]), int(inst["price_decimals"])
        self.min_notional = _d(inst["min_notional"])

    def _check_expiry(self, expires_at) -> None:
        if not expires_at:
            return
        when = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")).astimezone(timezone.utc)
        left = when.timestamp() - time.time()
        if left <= 0:
            raise PolymarketError("credencial proxy EXPIRADA: gere outra (deploy/polymarket-proxy.py)")
        if left < self.EXPIRY_WARN_S:
            log.warning("credencial proxy do Polymarket expira em %.1f h", left / 3600)

    # ---- HTTP ---------------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, *, params=None, body=None, headers=None):
        r = self.http.request(method, self.base + path, params=params, json=body, headers=headers or {}, timeout=15)
        if r.status_code >= 400:
            raise PolymarketError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def _get(self, path: str, params: dict | None = None, *, auth: bool = True):
        headers = {"POLYMARKET-PROXY": self.proxy, "POLYMARKET-SECRET": self.secret} if auth else {}
        return self._call("GET", path, params=params, headers=headers)

    def _command(self, method: str, path: str, signed_op: list, body_op: dict):
        salt, ts = secrets.randbits(32), int(time.time() * 1000)
        body = {"op": body_op, "sig": self.sign(self.key, signed_op, salt=salt, ts=ts, chain_id=self.chain_id),
                "salt": salt, "ts": ts}
        res = self._call(method, path, body=body)
        acks = res if isinstance(res, list) else [res]
        for a in acks:
            if a.get("status") == "err":
                raise PolymarketError(f"comando recusado: {a.get('error')}")
        return acks

    # ---- Executor -----------------------------------------------------------------------------------------------
    def position(self) -> Position | None:
        for p in self._get("/v1/account/portfolio")["positions"]:
            if int(p["instrument_id"]) == self.iid and _d(p["size"]) != 0:
                size = _d(p["size"])
                return Position(1 if size > 0 else -1, float(abs(size)), float(p["entry_price"]))
        return None

    def _bbo(self) -> tuple[Decimal, Decimal]:
        rows = self._get("/v1/info/bbo", {"instrument_id": self.iid}, auth=False)
        if not rows:
            raise PolymarketError("sem BBO para o instrumento")
        return _d(rows[0]["bid_price"]), _d(rows[0]["ask_price"])

    def _q(self, x: Decimal, dec: int, rounding) -> Decimal:
        return x.quantize(Decimal(1).scaleb(-dec), rounding=rounding)

    def market_order(self, side: int, qty: float, price_hint: float, reduce_only: bool = False) -> Fill:
        if side not in (-1, 1) or qty <= 0:
            raise ValueError("side deve ser +1/-1 e qty > 0")
        bid, ask = self._bbo()
        buy = side == 1
        limit = self._q((ask if buy else bid) * (1 + self.SLIPPAGE * side), self.px_dec,
                        ROUND_CEILING if buy else ROUND_FLOOR)
        q = self._q(_d(qty), self.qty_dec, ROUND_FLOOR)
        if q <= 0 or q * limit < self.min_notional:
            raise PolymarketError(f"ordem de {q} a {limit} abaixo do notional minimo {self.min_notional}")
        coid = uuid.uuid4().hex
        row = [self.iid, buy, _fmt(limit), _fmt(q), "ioc", False, True if reduce_only else None, coid, None]
        body_row = {"iid": self.iid, "buy": buy, "po": False, "qty": _fmt(q), "tif": "ioc", "p": _fmt(limit), "c": coid}
        if reduce_only:
            body_row["ro"] = True
        acks = self._command("POST", "/v1/trade/orders", ["createOrders", [row]],
                             {"type": "createOrders", "args": [body_row]})
        oid = int(acks[0]["oid"])
        order = self._settle(oid)
        filled = _d(order.get("filled_quantity") or 0)
        if filled <= 0:
            raise PolymarketError(f"ordem IOC sem fill (status={order.get('status')}, limite {limit}, "
                                  f"bid={bid} ask={ask})")
        price, fee = self._fills(oid, float(limit))
        if filled < q:
            log.warning("fill parcial: %s de %s", filled, q)
        return Fill(side, float(filled), price, fee)

    def _settle(self, oid: int) -> dict:
        order: dict = {}
        for _ in range(self.SETTLE_TRIES):
            rows = self._get("/v1/account/orders", {"order_id": oid, "instrument_id": self.iid})
            order = rows[0] if rows else {}
            if order.get("status") in TERMINAL:
                break
            time.sleep(self.SETTLE_DELAY_S)
        return order

    def _fills(self, oid: int, fallback_price: float) -> tuple[float, float]:
        """Preco medio ponderado e taxa total dos fills da ordem; sem fills, usa o limite e taxa 0 (e avisa)."""
        data = self._get("/v1/account/fills", {"instrument_id": self.iid}).get("data", [])
        mine = [t for t in data if int(t["order_id"]) == oid]
        if not mine:
            log.warning("fills da ordem %s indisponiveis; usando o limite %.4f e taxa 0", oid, fallback_price)
            return fallback_price, 0.0
        qty = sum(_d(t["quantity"]) for t in mine)
        px = sum(_d(t["price"]) * _d(t["quantity"]) for t in mine) / qty
        return float(px), float(sum(_d(t.get("total_fee") or t["fee"]) for t in mine))

    def place_stop(self, side: int, qty: float, stop_price: float) -> str | None:
        buy = side == 1  # lado da ordem de saida
        px = self._q(_d(stop_price), self.px_dec, ROUND_CEILING if buy else ROUND_FLOOR)
        row = [self.iid, buy, None, "0", None, False, True, None, [True, _fmt(px), "sl"]]
        body_row = {"iid": self.iid, "buy": buy, "po": False, "qty": "0", "ro": True,
                    "tr": {"tpsl": "sl", "trp": _fmt(px), "market": True}}
        acks = self._command("POST", "/v1/trade/orders", ["createOrders", [row], "position"],
                             {"type": "createOrders", "args": [body_row], "grp": "position"})
        return str(acks[0]["oid"])

    def _stops(self) -> list[dict]:
        rows = self._get("/v1/account/open-orders", {"instrument_id": self.iid})
        return [o for o in rows if (o.get("tpsl") or {}).get("kind") == "sl"]

    def cancel_stops(self) -> None:
        ids = [int(o["order_id"]) for o in self._stops()]
        if ids:
            self._command("DELETE", "/v1/trade/orders", ["cancelOrders", ids], {"type": "cancelOrders", "args": ids})

    def has_stop(self) -> bool | None:
        return bool(self._stops())
