# Dados

Scripts que baixam dados publicos e gratuitos para `dados/raw/` (ignorado pelo git; reproduzivel).
Precisam apenas de `pandas` e da biblioteca padrao do Python.

| Script | Fonte | Exemplo |
|---|---|---|
| `fetch_binance.py` | data.binance.vision (spot, klines mensais) | `python dados/fetch_binance.py BTCUSDT 1m 2023-01 2024-12` |
| `fetch_bcb.py` | SGS do Banco Central | `python dados/fetch_bcb.py` (catalogo: Selic, CDI, IPCA, IGP-M, dolar, desemprego) |

Pendentes: Dukascopy (forex/indices), Yahoo/Stooq (acoes), FRED (macro EUA), curvas ANBIMA/Tesouro.

Antes de usar qualquer fonte, confira os termos de uso dela.
