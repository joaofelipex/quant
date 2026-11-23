"""Executores de ordem. A estrategia nunca conhece a corretora: so fala com esta interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Fill, Position


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

    def __init__(self, symbol: str, api_key: str, secret: str, testnet: bool = True):
        import ccxt  # import tardio: so quem opera na corretora precisa instalar

        self.symbol = symbol
        self.ex = ccxt.binanceusdm({"apiKey": api_key, "secret": secret, "enableRateLimit": True})
        if testnet:
            self.ex.set_sandbox_mode(True)
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

    def market_order(self, side: int, qty: float, price_hint: float, reduce_only: bool = False) -> Fill:
        qty = float(self.ex.amount_to_precision(self.symbol, qty))
        params = {"reduceOnly": True} if reduce_only else {}
        o = self.ex.create_order(self.symbol, "market", "buy" if side == 1 else "sell", qty, None, params)
        price = float(o.get("average") or o.get("price") or price_hint)
        fee = sum(float(f.get("cost") or 0) for f in (o.get("fees") or []))
        return Fill(side, qty, price, fee)
