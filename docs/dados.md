# Dados

Scripts que baixam dados publicos e gratuitos para `dados/raw/` (ignorado pelo git; reproduzivel).
Precisam apenas de `pandas` e da biblioteca padrao do Python.

| Script | Fonte | Exemplo |
|---|---|---|
| `src/quant/data/fetch_binance.py` | data.binance.vision (spot, klines mensais) | `python -m quant.data.fetch_binance BTCUSDT 1m 2023-01 2024-12` |
| `src/quant/data/fetch_bcb.py` | SGS do Banco Central | `python -m quant.data.fetch_bcb` (catalogo: Selic, CDI, IPCA, IGP-M, dolar, desemprego) |

Pendentes: Dukascopy (forex/indices), Yahoo/Stooq (acoes), FRED (macro EUA), curvas ANBIMA/Tesouro.

Antes de usar qualquer fonte, confira os termos de uso dela.

## Dados curados (versionados)

`dados/curated/` guarda séries pequenas e já limpas no formato canônico (`datetime,open,high,low,close`,
ISO, ponto decimal). Exports do Profit (CSV/XLSX, vírgula decimal, `dd/mm/aaaa`) entram por
`quant.data.loaders.load_bars`; grave com `save_bars`. Nunca versione pickles.

| Arquivo | Conteúdo | Observação |
|---|---|---|
| `win_prev_5min.csv` | WIN 5 min, 15/04–14/09/2026 | Contrato anterior ao Z26. Abril–maio têm muitos dias esparsos. |
| `win_z26_5min.csv` | WINZ26 5 min, 12/05–16/10/2026 | Líquido só a partir de ~ago/2026. |
| `wdo_5min.csv` | WDO 5 min, 17/12/2025–16/10/2026 | Líquido a partir de ~31/08/2026; antes, quase vazio. |

As séries de WIN são **contratos diferentes** (não concatenar). Sem volume.
