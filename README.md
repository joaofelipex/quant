# quant

Pesquisa quantitativa multi-ativo (futuros B3, ações, renda fixa, macro, cripto). A pesquisa é em Python e agnóstica de plataforma; MT5 e Profit Pro são apenas destinos de execução.

```
src/quant/        biblioteca
  instruments.py    especificação de contrato (WIN, WDO, ...)
  data/             fetchers (Binance, Banco Central)
  backtest/         motor de backtest
  strategies/       estratégias (trend_follow, eth_flow_scalper)
  metrics.py        profit factor, Sharpe, Sortino, Calmar, t-stat, drawdown
  validation.py     split temporal, walk-forward, bootstrap de trades, stress de custos
estudos/          experimentos datados, cada um com README e resultados
  win_trend/        tendência no WIN (EMA + Donchian + filtro ER), treino/teste
  eth_flow/         scalper de fluxo no ETH futuro (1 dia de dado, só hipótese)
execucao/         adapters de plataforma (mt5/, profitpro/)
docs/             base conceitual (conceitos/) e fontes de dados (dados.md)
dados/raw/        dados baixados (fora do git, reproduzíveis)
```

## Uso

```bash
pip install -e .
python -m quant.data.fetch_bcb
python -m quant.data.fetch_binance BTCUSDT 1m 2024-01 2024-12
python estudos/win_trend/run_backtest.py
```

```python
from quant.instruments import Instrument
from quant.backtest.engine import run_backtest
from quant.validation import bootstrap_trades, stress_costs
```

Para outro ativo, defina um `Instrument` e passe `instrument=` ao `run_backtest`.

## Regra do repo

Nenhuma estratégia vai para `execucao/` sem: resultado fora da amostra, custos realistas, `stress_costs` e `bootstrap_trades` favoráveis. Checklist completo em `docs/conceitos/06_validacao_backtest.md`.
