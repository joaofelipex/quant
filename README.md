# Quant — MetaTrader 5

Base quant em MQL5: EA modular, indicador de sinal e script de diagnóstico.

## Estrutura

```
mql5/
  Experts/QuantStarter/     # EA (estratégia + risco + execução)
  Indicators/               # QuantMomentum (EMAs + setas)
  Scripts/                  # SymbolDiagnostics
```

## Instalação no MT5

1. Abra o MT5 → **Arquivo → Abrir Pasta de Dados**
2. Copie o conteúdo de `mql5/` para a pasta `MQL5/` do terminal:
   - `Experts/QuantStarter` → `MQL5/Experts/QuantStarter`
   - `Indicators/QuantMomentum.mq5` → `MQL5/Indicators/`
   - `Scripts/SymbolDiagnostics.mq5` → `MQL5/Scripts/`
3. No **MetaEditor** (F4), compile cada `.mq5` com **F7**
4. No gráfico: ative **Algo Trading** e arraste o EA

## Estratégia (QuantStarter)

| Bloco | Lógica |
|-------|--------|
| Sinal | Cruzamento EMA rápida × lenta (barra fechada) |
| Filtro | ATR mínimo em pontos (evita mercado morto) |
| Stops | SL/TP = ATR × fatores configuráveis |
| Risco | Lote calculado para arriscar X% do equity |
| Circuito | Para de operar se perda diária ≥ limite |

Comece no **Strategy Tester** (Ctrl+R) com conta demo antes de qualquer conta real.

## Próximos passos sugeridos

- Otimizar EMAs/ATR no tester (walk-forward)
- Adicionar filtro de sessão (Londres/NY)
- Exportar trades e analisar em Python
- Segunda estratégia (mean reversion) no mesmo esqueleto
