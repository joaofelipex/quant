# 06 · Validação de backtest

Objetivo: separar edge real de sorte e de ajuste ao passado.

## Tamanho de amostra
- t-stat do Sharpe: `t ≈ SR_por_período × √n`. Em anualizado: `t ≈ SR_anual × √anos`.
- Erro-padrão do Sharpe (por período): `√((1 + 0,5·SR²)/n)`.
- Exemplo: Sharpe anual 1,0 em 1 ano ⇒ t ≈ 1, inconclusivo. Precisa de ~4 anos para t ≈ 2.
- Referência de trades: ao menos algumas centenas, e em mais de um regime de mercado.

## Separação dos dados
- Treino / validação / teste: o teste é usado **uma vez**.
- Walk-forward: otimiza em janela `[t, t+N]`, opera `[t+N, t+N+M]`, desliza. É o padrão mínimo.
- Purga e embargo: remova observações sobrepostas entre treino e teste quando há sinais com janela longa.

## Viéses
- Look-ahead: usar informação que não existia (indicador com candle ainda aberto, preço ajustado futuro).
- Survivorship: universo só com ativos que sobreviveram.
- Data snooping / múltiplos testes: ao testar `N` variações, o melhor resultado tende a ser sorte. Ajuste o limiar de significância (Bonferroni) ou use *Deflated Sharpe Ratio*.
- Overfitting: parâmetros "ótimos" no treino que somem no teste (já ocorreu no `profitpro` com R:R 1:2,5).
- Execução irreal: ordens a mercado no fechamento, sem slippage, sem spread.

## Robustez
- Sensibilidade de parâmetros: um bom parâmetro tem um **platô** à volta, não um pico isolado.
- Monte Carlo / bootstrap dos trades: distribuição de drawdown e de PnL final.
- Troca de ativo e de período: a ideia generaliza?
- Custos pessimistas: dobre slippage e taxas; o resultado ainda se sustenta?

## Checklist antes de operar
1. Resultado positivo fora da amostra, com custos realistas.
2. Mais de ~100 trades no teste e mais de um regime.
3. Sensibilidade a parâmetros com platô.
4. Drawdown máximo aceitável para o capital real.
5. Simulador por 4-8 semanas batendo com o backtest.
6. Regras de parada: perda diária, perda total, desligar o robô.

## Armadilha-mãe
Quanto mais você mexe nos parâmetros olhando o resultado, menos o backtest vale.
