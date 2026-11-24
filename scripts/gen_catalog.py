"""Gera src/quant/live/catalog.json dos mercados ATIVOS ``KX<ID>PERP1`` da Kalshi (endpoint publico, sem chave).

    python scripts/gen_catalog.py [demo|prod]      # padrao: demo

O catalogo vai no pacote (o painel valida a escolha sem rede). Rode de novo quando a Kalshi listar mercados novos.
"""
import json
import re
import sys
from pathlib import Path

import requests

HOSTS = {"demo": "https://external-api.demo.kalshi.co", "prod": "https://api.elections.kalshi.com"}


def main(env: str = "demo") -> None:
    markets = requests.get(f"{HOSTS[env]}/trade-api/v2/margin/markets", timeout=30).json()["markets"]
    out = []
    for m in markets:
        mt = re.fullmatch(r"KX([A-Z0-9]+)PERP1", m["ticker"])
        if not mt or m.get("status") != "active":
            continue
        title = re.sub(r"^(Test )?(Equity|Index|Metal|Energy|FX|Crypto)\s+", "", m.get("title") or mt.group(1))
        title = re.sub(r"^[\d.]+\s+", "", title.replace(" Perp", ""))  # "0.01 AAVE" -> "AAVE"
        title = re.sub(r"PERP$", "", title)
        out.append({"id": mt.group(1), "ticker": m["ticker"], "title": title.strip() or mt.group(1),
                    "cls": m.get("asset_class") or "Outros"})
    out.sort(key=lambda x: (x["cls"], x["id"]))
    path = Path(__file__).resolve().parents[1] / "src" / "quant" / "live" / "catalog.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} mercados -> {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo")
