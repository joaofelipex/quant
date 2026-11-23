from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fill:
    side: int  # +1 compra, -1 venda
    qty: float
    price: float
    fee: float = 0.0


@dataclass(frozen=True)
class Position:
    side: int  # +1 long, -1 short
    qty: float
    entry: float
