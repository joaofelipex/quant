# Quant — MetaTrader 5

Base quant em MQL5 + análise de performance em Python.

## Estrutura

```
mql5/
  Experts/QuantStarter/   # EA modular (momentum / mean reversion)
  Indicators/             # QuantMomentum
  Scripts/                # SymbolDiagnostics
python/
  analyze_trades.py       # métricas + equity curve a partir do CSV MT5
  data/                   # coloque aqui os exports do tester
  reports/                # PNGs e summaries gerados
```

## Instalação no MT5

1. MT5 → **Arquivo → Abrir Pasta de Dados**
2. Copie o conteúdo de `mql5/` para `MQL5/` do terminal
3. MetaEditor (**F4**) → compile com **F7**
4. Ative **Algo Trading** e arraste o EA no gráfico
5. Valide no **Strategy Tester** (**Ctrl+R**) em demo

## Estratégias (QuantStarter v1.10)

| Modo | Sinal |
|------|--------|
| Momentum | Cruzamento EMA rápida × lenta (barra fechada) + ATR mínimo |
| Mean reversion | Close fora das Bollinger + RSI oversold/overbought |

**Comum a ambos:** SL/TP em ATR, risco % do equity, limite de perda diária, filtro de sessão (Londres / NY / overlap).

Ajuste os horários de sessão para o **fuso do servidor** do seu broker (não o horário local).

## Análise Python

```bash
cd python
pip install -r requirements.txt
python analyze_trades.py data/sample_trades.csv
```

Exporte deals do Strategy Tester ou do histórico da conta para `python/data/` e rode o script no CSV. Gera:

- métricas no terminal (win rate, profit factor, max DD, expectancy)
- `reports/equity_*.png`
- `reports/summary_*.csv`

## Fluxo recomendado

1. Backtest no Strategy Tester (cada modo de estratégia)
2. Exportar deals → `python/analyze_trades.py`
3. Ajustar sessão / ATR / risco e repetir (walk-forward manual)
4. Só então considerar conta demo com Algo Trading real
