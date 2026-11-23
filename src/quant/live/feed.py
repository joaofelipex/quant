"""Fontes de barras fechadas no formato canonico (datetime[UTC naive], open, high, low, close)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

TIMEFRAME_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}


class Feed(ABC):
    @abstractmethod
    def closed_bars(self, n: int) -> pd.DataFrame:
        """Ultimas ``n`` barras JA FECHADAS (nunca a barra em formacao: evita look-ahead)."""


class CcxtFeed(Feed):
    """Polling REST via ccxt. Simples e robusto; troque por WebSocket depois se a latencia importar."""

    def __init__(self, symbol: str, timeframe: str = "5m", testnet: bool = False, testnet_kind: str = "testnet"):
        import ccxt

        from .executor import configure_venue

        self.symbol, self.timeframe = symbol, timeframe
        self.ex = ccxt.binanceusdm({"enableRateLimit": True})
        configure_venue(self.ex, testnet, testnet_kind)

    def closed_bars(self, n: int) -> pd.DataFrame:
        raw = self.ex.fetch_ohlcv(self.symbol, self.timeframe, limit=n + 1)[:-1]  # descarta a barra aberta
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df.pop("ts"), unit="ms")
        return df[["datetime", "open", "high", "low", "close"]]
