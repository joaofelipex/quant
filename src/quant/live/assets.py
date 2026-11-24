"""Ativos que o runner pode operar na Kalshi: perpetuos de cripto com barras publicas na Binance (mesmo simbolo).

Conferida contra a API da Kalshi demo: cada um tem o mercado ``KX<ATIVO>PERP1`` ativo e o par ``<ATIVO>USDT`` no
feed publico. Fora: tickers que parecem cripto mas sao acoes (ex.: KXCPERP1 = Citigroup, KXCVXPERP1 = Chevron).
"""
from __future__ import annotations

CRYPTO = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "LINK", "LTC", "BCH", "DOT", "NEAR", "UNI", "AAVE", "SUI",
          "XLM", "HBAR", "HYPE", "WLD", "ZEC")


def symbol(asset: str) -> str:
    """Simbolo do feed (formato ccxt de perpetuo; o feed publico vira ``ETHUSDT``)."""
    return f"{asset}/USDT:USDT"


def ticker(asset: str) -> str:
    return f"KX{asset}PERP1"


def parse(spec: str) -> list[str]:
    """``"BTC,eth"`` -> ``["BTC", "ETH"]``; ``"todos"``/``"all"`` -> todos. ValueError se algum nao existir."""
    spec = (spec or "").strip()
    if spec.lower() in ("todos", "all"):
        return list(CRYPTO)
    out: list[str] = []
    for a in (x.strip().upper() for x in spec.split(",")):
        if not a:
            continue
        if a not in CRYPTO:
            raise ValueError(f"ativo desconhecido: {a!r} (validos: {', '.join(CRYPTO)})")
        if a not in out:
            out.append(a)
    return out
