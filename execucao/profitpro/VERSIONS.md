# Robôs NTSL — versões e status

Fonte de verdade da lógica é Python (`src/quant`). Os `.ntsl` são adapters; nenhum deles tem edge comprovado
(ver `estudos/win_trend/README.md`). **Use apenas em simulador.**

## Linhas de código

| Linha | O que é | Relação com a pesquisa |
|---|---|---|
| **v10** | EMA + Donchian + ATR + filtro de regime ER, saídas `ToCover` corretas | Porte fiel da estratégia do estudo `win_trend`. É o único NTSL que corresponde a algo testado em Python. |
| **v11 → v14** | EMA 9/21 + MACD + filtro de tendência lenta (EMA 27/63 ≈ 9/21 em 15 min) | Linha do usuário (cruzamento). Sem equivalente validado em `src/`; sem edge nos testes exploratórios. |
| `WdoTrendBot_v1` | v11-like para WDO, stop 8 / alvo 16 pts | Perdeu em todos os stops testados (`estudos/win_trend/diario.md`). Não usar. |
| `EthFlowScalper`, `ScalperMomentum` | Scalpers de fluxo/momentum | Não testados no editor; ver `estudos/eth_flow`. |

## Linha do tempo da linha v11–v14

| Versão | Mudança | Estado |
|---|---|---|
| v10 | Corrige `BuyToCover`/`SellToCover` invertidos (a posição nunca fechava) | Compila no editor |
| v11 | Saídas corretas, sem pirâmide, filtro lento, zera às 17:50 | Não compilada em produção |
| v12 | + máx. de entradas e de stops por dia | Não compilada |
| v13 | Stop/alvo como ordens OCO no book, perda diária em R$ | **Compilou mas não operou** (provável `Date[1]`, ver abaixo) |
| v14 | v13 sem `Date[1]`, entradas por `BuyPosition/SellPosition`, plots de debug | Pendente de teste no Profit |

## `legacy/`

Versões históricas, mantidas só para rastrear bugs. Não compile.

| Arquivo | Bug / nota |
|---|---|
| `WinTrendBot_v2_ORIGINAL_com_bug_piramide` | Recompra a cada candle com sinal; **e** saídas invertidas (posição nunca fecha). Risco ilimitado. |
| `v1`–`v9` | Evolução da v2 até a v9 (debug). Nas v2–v9 as saídas estão invertidas; só a v10 corrige. |
| `WinTrendBot.ntsl` | Primeiro rascunho, nomes de função não confirmados. |
