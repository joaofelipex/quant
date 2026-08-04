# QuantSage — Clear / B3

Bot quant com **regime + score de edge + risco**. Foco: **WIN** na Clear (também ações).

## Ideia (o “sábio”)

| Estado (Efficiency Ratio) | Comportamento |
|---------------------------|---------------|
| **TREND** (ER alto) | Segue tendência (EMA + RSI) |
| **RANGE** (ER baixo) | Mean reversion (z-score + RSI) |
| **CHAOS** (meio) | **Não opera** — sem edge claro |

Só entra se **score ≥ 70**, spread barato vs ATR, dentro da sessão B3, e com sizing por risco% × qualidade do setup × volatilidade.

## No Clear (importante)

1. **Não use F5/debugger** do MetaEditor — isso remove o EA ao parar  
2. Navegador (**Ctrl+N**) → **Atualizar** → arraste **`QuantSage`** (ou `QuantSageBot`) no gráfico  
3. Tem que aparecer o painel `QuantSage v2.00` no canto (**mesmo de madrugada**, via timer)  
4. Botão **Algo Trading** verde  
5. Login Clear válido (sem `Invalid account`)  
6. Backtest: **Ctrl+R** a qualquer hora  

## Símbolos Clear

- WIN: `WIN$` / `WIN$N` · sessão Futures Day  
- Ações: `PETR4`… · mude sessão para Equity  

## Instalação dev

Código em `mql5/Experts/QuantSage/`. Copiar para a pasta MQL5 do terminal Clear e compilar (F7).
