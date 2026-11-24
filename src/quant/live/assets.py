"""Ativos que o runner opera na Kalshi: o catalogo dos perpetuos ``KX<ID>PERP1`` ativos (acoes, cripto, cambio, metais,
indices...), gerado por ``scripts/gen_catalog.py`` (``catalog.json``, no pacote: o painel valida sem rede).

Preco: os 20 cripto de ``CRYPTO`` usam as barras publicas da Binance (como sempre); o resto usa as velas da propria
Kalshi (``KalshiFeed``), que existem para cada mercado.
"""
from __future__ import annotations

import json
from pathlib import Path

# cripto com par spot de mesmo preco na Binance (feed publico, historico longo)
CRYPTO = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "LINK", "LTC", "BCH", "DOT", "NEAR", "UNI", "AAVE", "SUI",
          "XLM", "HBAR", "HYPE", "WLD", "ZEC")

CLASS_LABEL = {"Crypto": "Cripto", "Equities": "Ações", "FX": "Câmbio", "Metals": "Metais", "Indices": "Índices",
               "GPU": "GPU", "Energy": "Energia"}


def _load() -> dict[str, dict]:
    path = Path(__file__).with_name("catalog.json")
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    return {r["id"]: r for r in rows}


CATALOG: dict[str, dict] = _load()
ALL = tuple(CATALOG)


def symbol(asset: str) -> str:
    """Simbolo do feed da Binance (formato ccxt de perpetuo; o feed publico vira ``ETHUSDT``). So para ``CRYPTO``."""
    return f"{asset}/USDT:USDT"


def ticker(asset: str) -> str:
    return CATALOG[asset]["ticker"] if asset in CATALOG else f"KX{asset}PERP1"


def uses_binance(asset: str) -> bool:
    return asset in CRYPTO


def rows() -> list[dict]:
    """Catalogo para o painel: ``[{id, ticker, title, cls, label, binance}]``, ja ordenado por classe e id."""
    return [{**r, "label": CLASS_LABEL.get(r["cls"], r["cls"]), "binance": r["id"] in CRYPTO} for r in CATALOG.values()]


def parse(spec: str) -> list[str]:
    """``"BTC,nvda"`` -> ``["BTC", "NVDA"]``; ``"todos"`` = os 20 cripto da Binance; ``"tudo"`` = o catalogo inteiro.
    ValueError se algum nao existir."""
    spec = (spec or "").strip()
    if spec.lower() in ("todos", "all"):
        return list(CRYPTO)
    if spec.lower() in ("tudo", "everything"):
        return list(ALL)
    out: list[str] = []
    for a in (x.strip().upper() for x in spec.split(",")):
        if not a:
            continue
        if a not in CATALOG:
            raise ValueError(f"ativo desconhecido: {a!r} (veja a lista em Operar > Ativos)")
        if a not in out:
            out.append(a)
    return out
