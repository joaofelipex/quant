# Quant — MetaTrader 5 (B3)

Stack quant para **B3** em MQL5 + análise de performance em Python.

## Estrutura

```
mql5/
  Experts/QuantStarter/   # EA (momentum / mean reversion + sessão B3)
  Indicators/             # QuantMomentum
  Scripts/                # SymbolDiagnostics (tick value / lote em R$)
python/
  analyze_trades.py
  data/
  reports/
```

## Instalação no MT5

1. MT5 → **Arquivo → Abrir Pasta de Dados**
2. Copie `mql5/` → pasta `MQL5/` do terminal
3. MetaEditor (**F4**) → **F7** em cada `.mq5`
4. No Market Watch, habilite o símbolo B3 (WIN, WDO, PETR4…)
5. Rode `SymbolDiagnostics` no gráfico antes do backtest
6. Strategy Tester (**Ctrl+R**) em demo

## Sessões B3 (defaults)

| Modo | Janela típica (Brasília) | Uso |
|------|--------------------------|-----|
| Equity | 10:00–17:55 | Ações / BDRs |
| Futures Day | 09:00–18:25 | WIN / WDO diurno |
| Futures Full | diurno + noturno | Day trade estendido |
| Custom | inputs livres | Seu horário |

Por padrão o EA **pula os primeiros 15 min** após a abertura (leilão/ruído) e **corta sexta às 16:30**.

Confirme se o relógio do servidor do broker = Brasília. Se estiver em GMT, use `Custom` ou ajuste.

## Estratégias (v1.20)

| Modo | Sinal |
|------|--------|
| Momentum | EMA 9×21 (barra fechada) + ATR opcional |
| Mean reversion | Bollinger + RSI |

Risco default mais conservador para B3: **0,5%** por trade, **2%** perda diária máx.

## Qual símbolo usar?

Depende do broker MT5 (Clear, XP, Genial, etc.):

- Mini índice: `WIN$`, `WIN$N`, ou vencimento `WINJ26`…
- Mini dólar: `WDO$`, `WDO$N`, `WDOJ26`…
- Ações: `PETR4`, `VALE3`, `ITUB4`…

Sempre valide **tick size / tick value** com o script de diagnóstico — o sizing de lote depende disso.

## Análise Python

```bash
cd python
pip install -r requirements.txt
python analyze_trades.py data/sample_trades.csv
```

## Fluxo B3 recomendado

1. `SymbolDiagnostics` no ativo (WIN ou ação)
2. Backtest no timeframe que você opera (M5/M15/H1)
3. Exportar deals → `analyze_trades.py`
4. Ajustar sessão / ATR / risco e repetir
5. Demo com Algo Trading antes de conta real
