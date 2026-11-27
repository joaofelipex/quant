# Pesquisa

## Regra de aprovação

Nenhuma estratégia vai para execução sem: resultado fora da amostra em período ou contrato não visto, custos
realistas, estresse de custos ×2, bootstrap favorável, **Sharpe deflacionado ≥ 0,95 contando as tentativas
descartadas** e teste contra uso de informação futura. Quem não passa fica em `estudos/` com o resultado negativo.

**Hoje: nenhuma aprovada.**

## Estudos

| Estudo | Pergunta | Resultado | Veredito |
|---|---|---|---|
| [win_trend](../estudos/win_trend/README.md) | Donchian + regime no mini índice 5 min | PF 1,27 no contrato anterior, 0,94 no seguinte; DSR 0,05–0,15 | inconclusivo |
| [ema_macd](../estudos/ema_macd/README.md) | robôs EMA + MACD em WIN e WDO | PF 0,7–1,1 | sem vantagem |
| [eth_flow](../estudos/eth_flow/README.md) | scalper de agressão no ETH futuro | 1 dia de dado (PF 1,57, 43 operações) | hipótese |
| [eth_ml](../estudos/eth_ml/README.md) | ML prevê o ETH em horas | AUC ~0,55; líquido negativo; melhor variante Sharpe 0,46, DSR 0,18 | reprovado |
| [tsmom_cripto](../estudos/tsmom_cripto/README.md) | tendência diária multiativo | Sharpe 0,80 no teste, t = 0,75, DSR 0,20 | reprovado |
| [xsmom_cripto](../estudos/xsmom_cripto/README.md) | momento transversal neutro | desenvolvimento −0,33, teste 1,04 | reprovado |
| [funding_carry](../estudos/funding_carry/README.md) | carry de funding | 5,2% a.a., com risco de liquidação em altas fortes | reprovado |
| [runner_eth_1m](../estudos/runner_eth_1m/README.md) | `trend_follow` em ETH 1 min | PF 0,26–0,64 em três anos | reprovado |
| [trend_eth_tf](../estudos/trend_eth_tf/README.md) | o mesmo em 15 min, 1 h, 4 h | 1 h: PF 0,73 e 1,07 | reprovado |
| [trend_19cripto](../estudos/trend_19cripto/README.md) | o mesmo em 19 cripto, 1 h | positivo nos dois anos com custo real; DSR baixo | **inconclusivo** (roda na demo) |
| [regras_historico](../estudos/regras_historico/README.md) | 8 regras simples de compra | nenhuma com t ≥ 3 | reprovado |
| [vela_30min](../estudos/vela_30min/README.md) | prever a próxima vela de 30 min | sinal menor que o custo | reprovado |
| [ia_intradia](../estudos/ia_intradia/README.md) | IA e regras intradia | entradas iguais ao acaso | reprovado |

Os backtests exploratórios de WIN e WDO no Profit (out/2026) também não acharam vantagem robusta; o diário está em
[`win_trend/diario.md`](../estudos/win_trend/diario.md).

## A candidata atual

`trend_follow`, 1 h, ER ≥ 0,5, canal 55, stop 2 ATR, tamanho por volatilidade, comprado e vendido, 19 criptos.

Com custo de 35 bps ida e volta e *funding* (25/11/2024 a 31/10/2026):

| | 1º ano | 2º ano |
|---|---|---|
| Retorno (soma dos retornos por operação, média entre ativos) | +105% | +21% |
| Sharpe | 0,99 | 0,86 |
| Queda máxima | −19% | −25% |

Ressalvas importantes:

- O 2º ano foi olhado várias vezes ao escolher variantes; o DSR no estudo (0,13 com 64 tentativas, com custo de
  10 bps) não separa o resultado do acaso.
- Dois anos de história e moedas muito correlacionadas.
- Os preços são da Binance; a execução é na demo da Kalshi.
- Só a prova em dados novos, daqui para a frente, resolve.

## Lições

1. **O custo decide.** Em barras curtas, taxa e *spread* consomem o sinal.
2. **AUC acima de 0,5 não é lucro.** Há sinais pequenos e reais que não pagam a execução.
3. **A demo engana.** A regra que passou na demo reprovou em preços de produção.
4. **Contar tentativas.** Com dezenas de variantes, um bom resultado aparece por acaso.
5. **Comparar com o acaso.** Entradas devem vencer horas sorteadas no mesmo ativo e lado.
6. **Filtro sem estudo custa.** O filtro de fluxo cortava cerca de metade do ganho simulado.
7. **Pré-registrar** o desenho antes de ver o resultado.

## Como fazer um estudo novo

1. Crie `estudos/<nome>/README.md` com hipótese, dados, regra de aprovação e número de variantes, **antes** de rodar.
2. Coloque o script ao lado e os relatórios em `reports/`.
3. Use `quant.backtest.engine`, o custo real da corretora e `quant.validation`.
4. Escreva o veredito, inclusive negativo, e acrescente a linha na tabela do [README](../README.md).

Teoria: [validação de backtest](conceitos/06_validacao_backtest.md).
