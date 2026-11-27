# Biblioteca, dados, testes e plataformas

## Instalação

Python 3.10 ou mais novo. Dependências base: pandas, numpy, matplotlib.

| Extra | Para |
|---|---|
| `dev` | pytest, ruff, openpyxl |
| `excel` | ler XLSX |
| `live` | ccxt (Binance) |
| `ml` | scikit-learn |
| `polymarket` | executor do Polymarket |

```bash
pip install -e ".[dev,live,ml]"
```

## Módulos (`src/quant`)

### Pesquisa

| Módulo | Conteúdo |
|---|---|
| `instruments` | especificação de contrato |
| `data.loaders` | `load_bars`, `check_bars`, `drop_illiquid_days`, `save_bars` |
| `data.fetch_binance`, `fetch_funding`, `fetch_bcb` | downloads públicos |
| `backtest.engine` | `run_backtest`, motor com execução pessimista |
| `strategies.trend_follow` | médias + regime ER + Donchian |
| `strategies.ema_macd` | cruzamento com MACD |
| `strategies.tsmom` | tendência diária com alvo de volatilidade |
| `strategies.funding_carry` | carry delta-neutro |
| `strategies.eth_flow_scalper` | agressão em *times & trades* |
| `metrics` | PF, Sharpe, Sortino, Calmar, queda máxima |
| `validation` | divisão temporal, *walk-forward*, Sharpe probabilístico e deflacionado, bootstrap, estresse de custos |
| `ml.features` | variáveis causais e rótulo |

### Operação

| Módulo | Conteúdo |
|---|---|
| `live.*` | robô, risco, feeds, executores, catálogo, paper da carteira ([robo.md](robo.md)) |
| `agent` | IA ([ia.md](ia.md)) |
| `control`, `accounts`, `auth`, `insight` | painel ([painel.md](painel.md)) |
| `manual` | boleta |
| `observ`, `flow`, `reconcile` | métricas, livro de ofertas, reconciliação |
| `alerts`, `selfcheck`, `dashboard` | avisos, autoverificação, painel estático do paper |

### Scripts

| Script | Faz |
|---|---|
| `scripts/gen_catalog.py` | catálogo de perpétuos da Kalshi |
| `scripts/pesquisa_tendencia.py` | pesquisa de tendência em cripto |
| `scripts/baixar_defillama.py` | base gratuita do DefiLlama |

## Convenções do backtest

- Sinal no fechamento da barra; ordem na abertura da seguinte.
- Se a barra abre além do stop, sai na abertura. Stop paga *slippage*; alvo não.
- Stop e alvo na mesma barra contam como stop.
- Uma operação por vez; nada dorme posicionado no motor intradiário.

Os estudos de cripto em 1 h usam simuladores próprios, nos scripts de cada pasta.

```python
from quant.data.loaders import load_bars
from quant.strategies import trend_follow as tf
from quant.backtest.engine import run_backtest
from quant.instruments import WIN
from quant.validation import deflated_sharpe_ratio

df = load_bars("dados/curated/win_z26_5min.csv", min_bars_per_day=60)
trades, m = run_backtest(tf.generate_signals(tf.add_indicators(df)), instrument=WIN)
deflated_sharpe_ratio(trades.pnl_brl, n_trials=20)
```

## Dados

- `dados/curated/`: WIN e WDO de 5 min, versionados, formato `datetime,open,high,low,close`.
- `dados/raw/`: downloads, fora do git.

Detalhes em [dados.md](dados.md).

## Testes e CI

Em 27/11/2026: **562 testes Python passando e 7 pulados**; **60 testes do painel** em 11 arquivos.

```bash
pytest
ruff check src tests estudos
cd web && npm test -- --watch=false
```

O GitHub Actions roda `ruff`, `pytest` (Python 3.10 e 3.12) e o estudo `win_trend` a cada push em `master`.
Os testes do painel Angular não estão no CI.

## Plataformas (`execucao/`)

| Pasta | Plataforma | Conteúdo |
|---|---|---|
| `mt5/` | MetaTrader 5 | EAs `QuantSage` e `QuantStarter`, indicador, script de diagnóstico, `analyze_trades.py` |
| `profitpro/` | Profit Pro | robôs NTSL; [VERSIONS.md](../execucao/profitpro/VERSIONS.md) e [notas da linguagem](../execucao/profitpro/NTSL_NOTAS.md) |

**Nenhum robô dessas pastas tem vantagem demonstrada: use só em simulador.** Não compile os arquivos de `legacy/`;
há versões com saídas invertidas que nunca fechavam a posição.
