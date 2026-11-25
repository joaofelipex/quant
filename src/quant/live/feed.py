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


class KalshiFeed(Feed):
    """Barras fechadas das velas PUBLICAS da Kalshi (sem chave): qualquer perpetuo (acoes, cambio, metais...).

    Os precos saem POR UNIDADE do ativo (vela / ``contract_size * underlying_multiplier``), a mesma convencao do feed da
    Binance, entao o executor e a estrategia nao percebem a diferenca. A Kalshi so tem velas de 1 e 60 min: 5m/15m saem
    de agregar as de 1 min (so baldes completos). Cada chamada devolve ate 300 velas (janelas maiores vem em pedacos) e,
    depois da primeira vez, so se busca o que falta (1 chamada por ciclo).
    """

    HOSTS = {"demo": "https://external-api.demo.kalshi.co", "prod": "https://api.elections.kalshi.com"}
    CHUNK = 300  # velas por chamada
    MAX_RANGE = 0.08  # vela com maxima/minima > 8% numa so barra de 1 min e dado ruim (a demo tem picos falsos)
    MAX_JUMP = 0.08   # fechamento a mais de 8% da mediana das ultimas velas tambem
    MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}

    def __init__(self, ticker: str, timeframe: str = "1m", env: str = "demo", *, now=None, fetch=get_json):
        if timeframe not in self.MINUTES:
            raise ValueError(f"timeframe {timeframe!r} nao suportado pelo feed da Kalshi ({', '.join(self.MINUTES)})")
        import time

        self.ticker, self.timeframe, self.minutes = ticker, timeframe, self.MINUTES[timeframe]
        self.base = f"{self.HOSTS[env]}/trade-api/v2/margin/markets/{ticker}"
        self.now, self.fetch = now or time.time, fetch
        self.rows: dict[int, tuple] = {}  # abertura (s) -> (o, h, l, c) das velas ja baixadas
        m = self.fetch(self.base)["market"]
        self.unit = float(m["contract_size"]) * float(m["underlying_multiplier"])

    def _candles(self, period: int, start: int, end: int) -> list[dict]:
        url = f"{self.base}/candlesticks?period_interval={period}&start_ts={start}&end_ts={end}"
        return self.fetch(url).get("candlesticks", [])

    def _ohlc(self, c: dict) -> tuple[float, float, float, float] | None:
        p = c.get("price") or {}
        if not all(p.get(k) not in (None, "") for k in ("open", "high", "low", "close")):
            b, a = c.get("bid") or {}, c.get("ask") or {}  # sem negocio no minuto: usa o meio do livro
            try:
                mid = [(float(b[k]) + float(a[k])) / 2 for k in ("open", "high", "low", "close")]
                return mid[0], mid[1], mid[2], mid[3]
            except (KeyError, TypeError, ValueError):
                return None
        return float(p["open"]), float(p["high"]), float(p["low"]), float(p["close"])

    def _drop_spikes(self, df: pd.DataFrame, factor: float = 1.0) -> pd.DataFrame:
        """Tira velas com pico falso (a demo da Kalshi tem): amplitude absurda ou fechamento longe da mediana vizinha.
        Um pico nao pode virar stop falso nem entrada falsa; a vela some e o ATR/estrategia seguem com as outras."""
        if len(df) < 3:
            return df
        wide = (df["high"] / df["low"].where(df["low"] > 0) - 1) > self.MAX_RANGE * factor
        med = df["close"].rolling(5, center=True, min_periods=3).median()
        far = (df["close"] / med - 1).abs() > self.MAX_JUMP * factor
        return df[~(wide | far).fillna(False)].reset_index(drop=True)

    def closed_bars(self, n: int) -> pd.DataFrame:
        now = int(self.now())
        native = self.minutes in (1, 60)
        period = self.minutes if native else 1
        step = period * 60
        end = now - now % step  # so periodos ja encerrados
        want = n if native else n * self.minutes + self.minutes  # velas de `period` min que precisamos
        floor = end - want * step
        # incremental: so busca o que falta depois da ultima vela guardada (1 chamada por ciclo em regime normal)
        need_from = max(max(self.rows) - step, floor) if self.rows else floor
        pos = end
        while pos > need_from:
            start = max(pos - self.CHUNK * step, need_from)
            for c in self._candles(period, start, pos):
                ohlc = self._ohlc(c)
                if ohlc is not None and int(c["end_period_ts"]) <= end:
                    self.rows[int(c["end_period_ts"]) - step] = ohlc  # chave = abertura da vela
            pos = start
        for k in [k for k in self.rows if k < floor]:
            del self.rows[k]
        if not self.rows:
            return pd.DataFrame({"datetime": pd.to_datetime([]), "open": [], "high": [], "low": [], "close": []})
        df = pd.DataFrame([(t, *v) for t, v in sorted(self.rows.items())],
                          columns=["ts", "open", "high", "low", "close"])
        df = self._drop_spikes(df, 1.0 if period == 1 else 2.5)  # velas de 1 h oscilam mais que as de 1 min
        if df.empty:
            return pd.DataFrame({"datetime": pd.to_datetime([]), "open": [], "high": [], "low": [], "close": []})
        if not native:
            bucket = self.minutes * 60
            df["b"] = df["ts"] // bucket * bucket
            cnt = df.groupby("b")["ts"].transform("count")
            df = df[(cnt == self.minutes) & (df["b"] + bucket <= end)]  # so baldes completos e ja fechados
            df = df.groupby("b").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                     close=("close", "last")).reset_index().rename(columns={"b": "ts"})
        df = df.tail(n)
        out = pd.DataFrame({"datetime": pd.to_datetime(df["ts"], unit="s")})
        for col in ("open", "high", "low", "close"):
            out[col] = (df[col] / self.unit).to_numpy()
        return out.reset_index(drop=True)
