# ema_macd — a linha de robôs NTSL v11–v14

**Status: sem edge. Não operar em conta real.**

Cruzamento EMA 9/21 confirmado por MACD, com stop/alvo fixos em pontos e, opcionalmente, filtro de tendência lenta
(EMA 27/63 em 5 min ≈ EMA 9/21 em 15 min). É a lógica que roda nos robôs `WinTrendBot_v11…v14` e `WdoTrendBot_v1`;
este estudo mede essa lógica sob o motor realista (`entry="next_open"`, gap, zeragem às 17:50, só dias líquidos).

```bash
python estudos/ema_macd/run_study.py     # reports/variantes.csv
```

## Resultado (1 contrato, alvo = 2 × stop, 1 tick de slippage)

| Caso | Dias | Trades | PF | PnL (R$) | DD (R$) | t | P(prej.) | DSR* |
|---|---|---|---|---|---|---|---|---|
| WIN anterior · sem filtro 300/600 | 62 | 167 | 0,85 | −972 | −1.574 | −0,98 | 84% | 0,01 |
| WIN anterior · filtro lento 300/600 | 62 | 52 | 0,94 | −115 | −777 | −0,21 | 59% | 0,05 |
| WINZ26 · sem filtro 300/600 | 47 | 146 | 0,97 | −165 | −1.194 | −0,17 | 56% | 0,05 |
| WINZ26 · filtro lento 300/600 | 47 | 47 | 1,09 | +148 | −796 | 0,27 | 40% | 0,11 |
| WINZ26 · filtro lento 400/800 | 47 | 44 | 1,28 | +493 | −497 | 0,72 | 23% | 0,22 |
| WDO · sem filtro 8/16 | 32 | 67 | 0,71 | −1.045 | −1.281 | −1,29 | 90% | 0,01 |
| WDO · filtro lento 8/16 | 32 | 25 | 0,78 | −245 | −595 | −0,51 | 70% | 0,03 |
| WDO · filtro lento 15/30 | 32 | 20 | 1,69 | +476 | −239 | 0,82 | 19% | 0,25 |

\* DSR deflacionado por 8 tentativas (as linhas desta tabela). Probabilidade de o edge ser real; ≥ 0,95 seria o mínimo.

## Leitura

- **Sem filtro o cruzamento perde** em todas as séries: o sinal é atrasado e dá muito falso positivo em lateralização.
- **O filtro lento corta ~70% dos trades e leva o resultado para perto de zero**, não para o lucro.
- **As linhas positivas são ajuste de stop**: WIN 400/800 e WDO 15/30 só aparecem porque o stop foi mexido
  depois de ver a perda. Com 20–44 trades, t < 1 e DSR ≈ 0,2, isso é indistinguível de ruído de seleção.
- Os limites diários dos robôs (v12+) protegem a conta mas não aparecem aqui; não criam edge.

## Limitações

Séries curtas (32–62 dias líquidos), contratos diferentes, sem volume, sem limites diários modelados.
O `macd()` nativo do Profit pode diferir marginalmente do MACD usado aqui.
