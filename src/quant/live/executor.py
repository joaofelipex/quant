"""Executores de ordem. A estrategia nunca conhece a corretora: so fala com esta interface."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from .models import Fill, Position

log = logging.getLogger("quant.live")


# Chaves de URL de futuros do ccxt que apontam para fapi.binance.com; no testnet legado todas vao para o host de teste.
LEGACY_TESTNET_HOST = "https://testnet.binancefuture.com"
CCXT_OPTIONS = {"enableRateLimit": True, "options": {"fetchCurrencies": False}}  # sem /sapi (moedas): so futuros


def configure_venue(ex, testnet: bool, kind: str = "testnet") -> None:
    """Aponta um objeto ccxt para o ambiente de teste da Binance. ``kind``: 'testnet' (sandbox legado de futuros,
    testnet.binancefuture.com) ou 'demo' (Demo Trading, demo-fapi.binance.com). As chaves de um NAO valem no outro.

    O 'testnet' troca so as URLs de futuros, sem ``set_sandbox_mode``: o ccxt recente recusa chamadas AUTENTICADAS de
    futuros nesse modo (ele foi descontinuado a favor do Demo Trading), mas o host legado segue respondendo.
    O 'demo' devolve 451 em IPs dos EUA; o 'testnet' legado responde de la.
    """
    if not testnet:
        return
    if kind == "demo":
        ex.enable_demo_trading(True)
    elif kind == "testnet":
        api = ex.urls["api"]
        for key, url in list(api.items()):
            if isinstance(url, str) and "https://fapi.binance.com" in url:
                api[key] = url.replace("https://fapi.binance.com", LEGACY_TESTNET_HOST)
    else:
        raise ValueError(f"QUANT_TESTNET_KIND invalido: {kind!r} (use 'testnet' ou 'demo')")


class InsufficientFunds(RuntimeError):
    """A corretora recusou a ordem de ENTRADA por falta de saldo/margem. Nao adianta repetir na mesma barra."""


class Executor(ABC):
    @abstractmethod
    def position(self) -> Position | None:
        """Posicao atual segundo a FONTE DE VERDADE (a corretora, no caso real)."""

    @abstractmethod
    def market_order(self, side: int, qty: float, price_hint: float, reduce_only: bool = False) -> Fill: ...

    def place_stop(self, side: int, qty: float, stop_price: float) -> str | None:
        """Stop PROTETOR na corretora; ``side`` = lado da ordem de saida. None = sem suporte (stop por software)."""
        return None

    def cancel_stops(self) -> None:  # noqa: B027
        """Cancela stops protetores pendentes."""

    def has_stop(self) -> bool | None:
        """Ha stop protetor ativo na corretora? ``None`` = nao sei / sem suporte (stop so por software)."""
        return None

    def export_state(self) -> dict | None:
        """Estado proprio a guardar junto com o do runner (so o paper: a corretora real ja guarda a posicao)."""
        return None

    def import_state(self, state: dict) -> None:  # noqa: B027
        """Restaura o que ``export_state`` devolveu."""

    def close_position(self, price_hint: float) -> Fill | None:
        pos = self.position()
        if pos is None:
            return None
        return self.market_order(-pos.side, pos.qty, price_hint, reduce_only=True)


class PaperExecutor(Executor):
    """Simula execucao a mercado com slippage e taxa proporcionais. Posicao liquida unica."""

    def __init__(self, slippage: float = 0.0005, fee_rate: float = 0.0004):
        self.slippage = slippage
        self.fee_rate = fee_rate
        self._pos: Position | None = None

    def position(self) -> Position | None:
        return self._pos

    def export_state(self) -> dict | None:
        p = self._pos
        return {"pos": {"side": p.side, "qty": p.qty, "entry": p.entry}} if p else {"pos": None}

    def import_state(self, state: dict) -> None:
        p = (state or {}).get("pos")
        self._pos = Position(int(p["side"]), float(p["qty"]), float(p["entry"])) if p else None

    def market_order(self, side: int, qty: float, price_hint: float, reduce_only: bool = False) -> Fill:
        if side not in (-1, 1) or qty <= 0:
            raise ValueError("side deve ser +1/-1 e qty > 0")
        price = price_hint * (1 + self.slippage * side)  # compra paga mais, venda recebe menos
        fee = price * qty * self.fee_rate
        if reduce_only:
            if self._pos is None or self._pos.side == side:
                raise ValueError("reduce_only sem posicao oposta para reduzir")
            self._pos = None
        else:
            if self._pos is not None:
                raise ValueError("ja ha posicao aberta (um trade por vez)")
            self._pos = Position(side, qty, price)
        return Fill(side, qty, price, fee)


class BinanceFuturesExecutor(Executor):
    """USD-M futures via ccxt. NAO TESTADO contra a exchange: valide na testnet antes de qualquer coisa.

    ``testnet=True`` usa o sandbox. Mainnet exige confirmacao explicita na config (ver config.py).
    """

    def __init__(self, symbol: str, api_key: str, secret: str, testnet: bool = True, testnet_kind: str = "testnet"):
        import ccxt  # import tardio: so quem opera na corretora precisa instalar

        self.symbol = symbol
        self.ex = ccxt.binanceusdm({"apiKey": api_key, "secret": secret, **CCXT_OPTIONS})
        configure_venue(self.ex, testnet, testnet_kind)
        self.ex.load_markets()

    def position(self) -> Position | None:
        for p in self.ex.fetch_positions([self.symbol]):
            contracts = float(p.get("contracts") or 0)
            if contracts:
                side = 1 if p["side"] == "long" else -1
                return Position(side, contracts, float(p["entryPrice"]))
        return None

    def place_stop(self, side: int, qty: float, stop_price: float) -> str | None:
        qty = float(self.ex.amount_to_precision(self.symbol, qty))
        price = float(self.ex.price_to_precision(self.symbol, stop_price))
        params = {"stopPrice": price, "reduceOnly": True}
        o = self.ex.create_order(self.symbol, "STOP_MARKET", "buy" if side == 1 else "sell", qty, None, params)
        return str(o["id"])

    def cancel_stops(self) -> None:
        self.ex.cancel_all_orders(self.symbol)

    def has_stop(self) -> bool | None:
        for o in self.ex.fetch_open_orders(self.symbol):
            if o.get("reduceOnly") and (o.get("stopPrice") or "stop" in str(o.get("type", "")).lower()):
                return True
        return False

    # fee de fallback (taker USD-M sem desconto) e tentativas de consulta ao fill; ajustaveis nos testes
    FALLBACK_FEE_RATE = 0.0004
    SETTLE_TRIES = 3
    SETTLE_DELAY_S = 0.5

    def market_order(self, side: int, qty: float, price_hint: float, reduce_only: bool = False) -> Fill:
        qty = float(self.ex.amount_to_precision(self.symbol, qty))
        params = {"reduceOnly": True} if reduce_only else {}
        order = self.ex.create_order(self.symbol, "market", "buy" if side == 1 else "sell", qty, None, params)
        order = self._settle(order)
        price = float(order.get("average") or 0)
        if price <= 0:
            log.warning("sem preco medio do fill da ordem %s; usando a referencia %.4f", order.get("id"), price_hint)
            price = price_hint
        filled = float(order.get("filled") or qty)
        return Fill(side, filled, price, self._fee(order, price, filled))

    def _settle(self, order: dict) -> dict:
        """A resposta imediata de uma ordem a mercado pode vir sem preco medio/taxa: consulta ate preencher."""
        o = order
        for _ in range(self.SETTLE_TRIES):
            if float(o.get("average") or 0) > 0 and o.get("status") in ("closed", "filled"):
                break
            time.sleep(self.SETTLE_DELAY_S)
            try:
                o = self.ex.fetch_order(o["id"], self.symbol)
            except Exception:  # noqa: BLE001 - segue com o que ha; o aviso sai em market_order
                log.exception("falha ao consultar a ordem %s", o.get("id"))
        return o

    def _fee(self, order: dict, price: float, qty: float) -> float:
        fees = order.get("fees") or ([order["fee"]] if order.get("fee") else [])
        if not fees:
            try:
                trades = self.ex.fetch_my_trades(self.symbol, params={"orderId": order["id"]})
                fees = [t["fee"] for t in trades if t.get("fee")]
            except Exception:  # noqa: BLE001
                log.exception("falha ao consultar trades da ordem %s", order.get("id"))
        usd = [f for f in fees if f.get("currency") in ("USDT", "USDC", "BUSD")]
        if fees and len(usd) == len(fees):
            return sum(float(f.get("cost") or 0) for f in usd)
        log.warning("taxa da ordem %s indisponivel ou fora de USDT; estimando %.2f bps", order.get("id"),
                    self.FALLBACK_FEE_RATE * 1e4)
        return price * qty * self.FALLBACK_FEE_RATE
