# Execução

Adapters que levam estratégias validadas em `src/quant` para uma plataforma. Nenhum deles é fonte de verdade: a pesquisa e o backtest vivem em Python.

| Pasta | Plataforma | Conteúdo |
|---|---|---|
| `mt5/` | MetaTrader 5 (Clear/B3) | EAs `QuantSage`, `QuantStarter`, indicador, scripts MQL5 e `analyze_trades.py` (relatório de deals) |
| `profitpro/` | Profit Pro (Nelogica) | Robôs NTSL (`VERSIONS.md` diz qual é qual), `legacy/` com versões com bug, `NTSL_NOTAS.md` com sintaxe e semântica de ordens |

Instalação MT5: copiar `mt5/mql5/` para a pasta MQL5 do terminal e compilar (F7). Não rodar com F5/debugger (remove o EA ao parar).

**Nenhum robô aqui tem edge demonstrado** (ver `estudos/`). Rode só em simulador. O único NTSL com equivalente
validado em Python é `WinTrendBot_v10_fix_ToCover.ntsl`.
