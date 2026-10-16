# Base de conceitos quantitativos

Biblioteca de fórmulas e métodos usados nas análises do projeto, separada por segmento.
Cada nota segue o mesmo molde: **o que é → fórmula → como usar → dado necessário → armadilhas**.

| Arquivo | Segmento | Para que serve |
|---|---|---|
| [00_fundamentos.md](00_fundamentos.md) | Base comum | Retorno, risco, métricas de desempenho, dimensionamento |
| [01_acoes.md](01_acoes.md) | Ações | Precificação, valuation, fatores, mean reversion, pairs |
| [02_renda_fixa.md](02_renda_fixa.md) | Renda fixa | Preço/yield, duration, curva de juros, DI e Tesouro |
| [03_macro.md](03_macro.md) | Macro | Juros reais, Taylor, câmbio, regimes, indicadores |
| [04_derivativos.md](04_derivativos.md) | Derivativos | Futuros, opções, Black-Scholes, gregas |
| [05_microestrutura_cripto.md](05_microestrutura_cripto.md) | Microestrutura e cripto | Fluxo, VWAP, custos, funding, basis |
| [06_validacao_backtest.md](06_validacao_backtest.md) | Validação | Como não se enganar com backtest |

## Convenções

- `P_t` preço, `r_t` retorno simples, `R_t = ln(P_t/P_{t-1})` retorno logarítmico.
- Dias úteis por ano: **252** (B3), **365** (cripto).
- `rf` taxa livre de risco (no Brasil, CDI/Selic).
- Fórmulas em texto simples para ler em qualquer editor.

## Fontes de dados por segmento (a preencher)

| Segmento | Fonte candidata (gratuita) | Status |
|---|---|---|
| Cripto | data.binance.vision | `dados/fetch_binance.py` pronto |
| Forex/índices | Dukascopy, HistData | pendente |
| Ações / ETFs | Yahoo (`yfinance`), Stooq | pendente |
| Macro | SGS do Banco Central (FRED para EUA) | `dados/fetch_bcb.py` pronto (FRED pendente) |
| Renda fixa BR | Tesouro Transparente, ANBIMA (curvas) | pendente |
| Futuros B3 (WIN/WDO/DI) | Profit/MT5 (exportação própria) | pendente |

> Os limites e termos de cada fonte devem ser conferidos antes do uso.
