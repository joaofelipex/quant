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
- Overfitting: parâmetros "ótimos" no treino que somem no teste (já ocorreu no estudo `win_trend` com R:R 1:2,5).
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

## Implementação no repo (`src/quant/validation.py`, `src/quant/backtest/engine.py`)

| Problema | Ferramenta | Nota |
|---|---|---|
| Look-ahead nos sinais | `tests/test_no_lookahead.py` | Trunca o futuro e exige sinais passados idênticos. Todo indicador novo entra aqui. |
| Execução otimista | `run_backtest(entry="next_open")` | Sinal no fechamento *i*, ordem na abertura *i+1*; gap atravessa o stop; stop paga slippage, alvo (limite) não; stop e alvo na mesma barra = stop. `entry="close"` só para medir quanto o modo otimista infla o resultado. |
| Dormir posicionado | `force_flat` | Zera no horário; virada de dia fecha como `overnight`. |
| Múltiplos testes | `deflated_sharpe_ratio(pnl, n_trials)` | `n_trials` conta **todas** as variantes olhadas, inclusive as descartadas. Resultado < 0,95 não descarta sorte de seleção. |
| Incerteza do PnL | `bootstrap_trades` | P(prejuízo) e quantis de PnL/drawdown reamostrando trades. |
| Custo pessimista | `stress_costs` | Slippage e taxa ×2, ×3. Edge que morre em ×2 não existe. |
| Janelas | `train_test_split_time`, `walk_forward_splits` | Teste disjunto e posterior ao treino. |

### Armadilhas de dado já encontradas neste repo

- **Contrato ilíquido**: a série WINZ26 tem dias com 2–10 barras (contrato recém-listado) e saltos de >8%
  entre barras. Indicadores sobre barras esparsas mentem. Use `load_bars(min_bars_per_day=60)` e `check_bars`.
- **Rolagem de contrato**: duas séries de WIN de vencimentos diferentes diferem em ~1,9% (carry). Nunca
  concatene; trate cada contrato como série própria e posições nunca atravessam a virada.
- **Amostras sobrepostas não são independentes**: dois contratos cobrindo as mesmas semanas veem o mesmo mercado.
