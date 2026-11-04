# quant

Pesquisa quantitativa multi-ativo (futuros B3, ações, renda fixa, macro, cripto). A pesquisa é em Python, testada e
agnóstica de plataforma; MT5 e Profit Pro são apenas destinos de execução. Princípio do repo: **o backtest tem que
tentar derrubar a estratégia**, não confirmá-la.

## Status da pesquisa

| Estudo | Hipótese | Resultado | Status |
|---|---|---|---|
| [`win_trend`](estudos/win_trend/README.md) | Donchian + regime ER no WIN 5 min | PF 1,27 no contrato anterior (t = 0,9), **0,94** no WINZ26; DSR 0,05–0,15 | inconclusivo |
| [`ema_macd`](estudos/ema_macd/README.md) | Cruzamento EMA + MACD (robôs NTSL v11–v14) em WIN e WDO | PF 0,7–1,1 sem filtro/com filtro; positivos só após ajustar stop | sem edge |
| [`eth_flow`](estudos/eth_flow/README.md) | Scalper de agressão no ETH futuro | 1 dia de dado | hipótese |

Nada acima está liberado para conta real. Diário do que já foi tentado: [`estudos/win_trend/diario.md`](estudos/win_trend/diario.md).

## Layout

```
src/quant/            biblioteca (instalável e testada)
  instruments.py        especificação de contrato (WIN, WDO, ...)
  data/                 loaders (Profit CSV/XLSX → barras canônicas), fetchers (Binance, Banco Central)
  backtest/engine.py    motor event-driven com execução pessimista
  strategies/           trend_follow (Donchian+ER), ema_macd, eth_flow_scalper
  metrics.py            PF, Sharpe, Sortino, Calmar, t-stat, drawdown
  validation.py         split temporal, walk-forward, bootstrap, stress de custos, Sharpe deflacionado
tests/                pytest: motor com contas feitas de cabeça, anti-look-ahead, loaders, validação
estudos/              experimentos datados; cada um com README, run script e reports/
execucao/             adapters de plataforma (mt5/, profitpro/) — nunca fonte de verdade
dados/curated/        séries limpas e versionadas (formato canônico); dados/raw/ é baixado e ignorado
docs/                 base conceitual (conceitos/) e fontes de dados (dados.md)
```

## Uso

```bash
pip install -e ".[dev]"
pytest && ruff check src tests estudos

python estudos/win_trend/run_backtest.py       # tearsheet do estudo WIN
python estudos/ema_macd/run_study.py           # variantes dos robôs NTSL
python -m quant.data.fetch_bcb                 # macro (SGS)
python -m quant.data.fetch_binance BTCUSDT 1m 2024-01 2024-12
```

```python
from quant.data.loaders import load_bars, check_bars
from quant.strategies import trend_follow as tf
from quant.backtest.engine import run_backtest
from quant.instruments import WIN
from quant.validation import bootstrap_trades, deflated_sharpe_ratio, stress_costs

df = load_bars("dados/curated/win_z26_5min.csv", min_bars_per_day=60)   # tira dias ilíquidos
sig = tf.generate_signals(tf.add_indicators(df))
trades, m = run_backtest(sig, instrument=WIN)        # entra na abertura seguinte, zera às 17:50
deflated_sharpe_ratio(trades.pnl_brl, n_trials=20)   # conte TODAS as variantes olhadas
```

Para outro ativo, defina um `Instrument` e passe `instrument=`; para stop fixo em pontos use `stop_col=`.

## Convenções de execução do motor

Sinal no fechamento *i* → ordem na abertura *i+1* · gap atravessa o stop (sai na abertura) · stop paga slippage,
alvo (limite) não · stop e alvo na mesma barra = stop · posição nunca dorme (`force_flat`, virada de dia fecha) ·
um trade por vez. Detalhes e armadilhas de dado em `docs/conceitos/06_validacao_backtest.md`.

## Regra do repo

Nenhuma estratégia vai para `execucao/` sem: resultado fora da amostra **em contrato/período não visto**, custos
realistas, `stress_costs` ×2 e `bootstrap_trades` favoráveis, **DSR ≥ 0,95 contando as tentativas descartadas** e
teste anti-look-ahead em `tests/`. A estratégia que não passa fica em `estudos/` com o resultado negativo escrito.
