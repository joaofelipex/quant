# Diário de pesquisa — WIN/WDO 5 min, out/2026

Registro do que foi tentado e descartado, para não repetir e para alimentar `n_trials` do Sharpe deflacionado.

> **Aviso de método.** Estas rodadas exploratórias usaram scripts avulsos, **antes** do motor realista e do filtro
> de dias líquidos (entrada no fechamento do sinal, sem gap, séries com dias esparsos). Os números abaixo são
> direcionais e **não reproduzíveis neste repo**. As conclusões que importam foram refeitas com o motor novo em
> `win_trend/README.md` e `ema_macd/README.md`.

## Ideias testadas (WIN 5 min, duas séries, com custos)

| Ideia | Resultado | Decisão |
|---|---|---|
| EMA 9/21 + MACD, stop/alvo 300/600 pts | PF ~1,1 (WINZ26, série sem filtro de liquidez) | linha `ema_macd` |
| + filtro de tendência lenta (EMA 27/63) | PF 1,2 numa série, 0,98 na outra | inconsistente |
| + stop em ATR (1,5–2×) em vez de pontos fixos | pior que pontos fixos | descartado |
| + breakeven após 1R | PF 1,04–1,09 | descartado |
| + máx. 2 trades/dia / perda diária | sem melhora de PF | mantido só como proteção operacional |
| + filtro VWAP aproximado (sem volume) | PF 1,1–1,45 conforme a série | descartado (sem volume não é VWAP) |
| Rompimento da faixa 9h–10h (ORB) | positivo só com filtro de range < 1.500 pts que exclui ~50% dos dias | descartado: filtro arbitrário |
| Reversão por Bollinger com ER < 0,3 | PF 0,70–0,82 | descartado |
| Recuo à EMA 21 a favor da tendência | PF 0,81 numa série, 1,11 na outra | descartado: sinal inverte |
| Viés da 1ª hora + cruzamento | PF 0,88–1,14 | descartado |
| Tempo gráfico 15/30/60 min | 15 min PF 1,63 (85 trades, instável ao stop); 30/60 min perdem | sem conclusão |
| Donchian + ER + ATR (estudo `win_trend`) | ver `README.md` do estudo | inconclusivo |
| WDO, EMA+MACD, stop 8/16 | prejuízo em todos os stops testados | descartado |

## Lições que viraram código

1. **Bugs de execução custaram mais que qualquer ajuste de parâmetro.** Saídas `ToCover` invertidas e pirâmide
   deixavam o risco ilimitado (`execucao/profitpro/NTSL_NOTAS.md`).
2. **Séries esparsas inflam resultado.** `load_bars(min_bars_per_day=60)` e `check_bars`.
3. **Entrada no fechamento do sinal é look-ahead de uma barra.** Padrão agora é `next_open`.
4. **Toda ideia olhada conta.** O README antigo tinha PF 1,45; com 20–100 tentativas o DSR é 0,05–0,15.
5. **Resultado que muda de sinal entre duas séries é ruído**, não "regime".
