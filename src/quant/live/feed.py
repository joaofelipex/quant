"""Fontes de barras fechadas no formato canonico (datetime[UTC naive], open, high, low, close)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from .http import get_json

TIMEFRAME_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}


class Feed(ABC):
    @abstractmethod
    def closed_bars(self, n: int) -> pd.DataFrame:
        """Ultimas ``n`` barras JA FECHADAS (nunca a barra em formacao: evita look-ahead)."""


class CcxtFeed(Feed):
    """Polling REST via ccxt. Simples e robusto; troque por WebSocket depois se a latencia importar."""

    def __init__(self, symbol: str, timeframe: str = "5m", testnet: bool = False, testnet_kind: str = "testnet"):
        import ccxt

        from .executor import CCXT_OPTIONS, configure_venue

        self.symbol, self.timeframe = symbol, timeframe
        self.ex = ccxt.binanceusdm(dict(CCXT_OPTIONS))
        configure_venue(self.ex, testnet, testnet_kind)

    def closed_bars(self, n: int) -> pd.DataFrame:
        raw = self.ex.fetch_ohlcv(self.symbol, self.timeframe, limit=n + 1)[:-1]  # descarta a barra aberta
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df.pop("ts"), unit="ms")
        return df[["datetime", "open", "high", "low", "close"]]


class PublicSpotFeed(Feed):
    """Barras de SPOT do endpoint publico de dados de mercado (sem chave, sem ccxt; responde de qualquer regiao).

    Para o paper: o perpetuo ``ETH/USDT:USDT`` vira o spot ``ETHUSDT``. A base spot-perp (poucos bps) e ignorada, entao
    isto serve a simulacao, nunca a ordens reais.
    """

    BASE = "https://data-api.binance.vision"

    def __init__(self, symbol: str, timeframe: str = "5m", base: str | None = None):
        self.symbol = symbol.split(":")[0].replace("/", "")  # ETH/USDT:USDT -> ETHUSDT
        self.timeframe = timeframe
        self.base = base or self.BASE

    def closed_bars(self, n: int) -> pd.DataFrame:
        raw = get_json(f"{self.base}/api/v3/klines?symbol={self.symbol}&interval={self.timeframe}&limit={n + 1}")[:-1]
        df = pd.DataFrame({"datetime": pd.to_datetime([r[0] for r in raw], unit="ms")})
        for col, i in (("open", 1), ("high", 2), ("low", 3), ("close", 4)):
            df[col] = [float(r[i]) for r in raw]
        return df
