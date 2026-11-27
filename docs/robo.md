# Robô de regras (`quant.live`)

Um processo (`quant-live`) com um *runner* por ativo. Código: [`runner.py`](../src/quant/live/runner.py),
[`multi.py`](../src/quant/live/multi.py), [`config.py`](../src/quant/live/config.py),
[`risk.py`](../src/quant/live/risk.py) e [`trend_follow.py`](../src/quant/strategies/trend_follow.py).

## O sinal

Calculado no fechamento de cada barra, só com dados até ela:

| Condição | Compra | Venda |
|---|---|---|
| Tendência (média exponencial rápida × lenta) | rápida acima | rápida abaixo |
| Regime: *efficiency ratio* ≥ `QUANT_ER` | sim | sim |
| Rompimento do canal Donchian das barras anteriores | fecha acima do topo | fecha abaixo do fundo |

## Um passo, na ordem

1. **Kill-switch:** se o arquivo `KILL` existe, fecha a posição, trava o risco e encerra.
2. **Reconciliação** com a corretora: posição fechada por fora (stop), entrada sem confirmação ou stop sumido.
3. **Stop** conferido em todas as barras desde a última processada. Se há lacuna de dados com posição aberta, fecha e trava.
4. **Saída por sinal oposto.**
5. **Entrada**, se não há posição, o sinal é válido, o ATR é positivo, o filtro de fluxo (se ligado) apoia e o risco libera.
6. **Proteção:** toda entrada ganha um stop na corretora. Se o stop não puder ser colocado, a posição é fechada e o ativo trava.
7. A barra só é marcada como processada depois de tudo. Se algo falha, o passo se repete em 5 s.

## Saídas

- Stop inicial a `QUANT_STOP_ATR` × ATR do preço de entrada.
- Sinal na direção oposta.
- *Trailing* opcional (`QUANT_TRAIL_ATR` > 0): o stop só anda a favor.
- Não há alvo de lucro.

## Tamanho

Com vários ativos (`QUANT_ASSETS`), cada entrada vale `QUANT_NOTIONAL` dólares, convertidos em contratos. Com
`QUANT_VOL_SIZE=1`, o valor é multiplicado por (ATR% típico ÷ ATR% atual), limitado a 0,5×–2×. Um ativo cujo menor
contrato passa de 1,5 × o valor por entrada fica de fora.

Com um único ativo, o tamanho é `QUANT_QTY`, e filtro de fluxo, *trailing* e ajuste por volatilidade **não são
aplicados**: só existem no modo de vários ativos.

## Risco

A decisão final antes de qualquer **entrada**; saídas nunca são bloqueadas.

| Trava | Regra | Sai sozinha? |
|---|---|---|
| Perda do dia por ativo | `QUANT_MAX_DAILY_LOSS` | sim, na virada do dia UTC |
| Perda do dia somada | `QUANT_MAX_TOTAL_LOSS` trava entradas de todos | sim |
| Operações por dia por ativo | 20 | sim |
| Dado atrasado | barra fechada há mais de 120 s | a cada barra |
| Kill-switch, posição órfã, falha de stop, lacuna, fechamento parcial | travam o ativo | **não**: use *Destravar risco* (admin) |

## Parâmetros

Editáveis pelo painel (validados em [`control.py`](../src/quant/control.py)); exigem reiniciar o robô.

| Variável | Faixa | Efeito |
|---|---|---|
| `QUANT_MODE` | `paper`, `testnet` | pelo painel não há `live` |
| `QUANT_VENUE` | `binance`, `kalshi` | corretora |
| `QUANT_TIMEFRAME` | 1m, 5m, 15m, 1h | tamanho da barra |
| `QUANT_ASSETS` | lista, `todos` ou `tudo` | vários ativos (só Kalshi demo) |
| `QUANT_NOTIONAL` | até 1000 | USD por entrada |
| `QUANT_QTY` | até 1 | quantidade fixa (um ativo) |
| `QUANT_DONCHIAN` | 2 a 500 | barras do canal |
| `QUANT_ER` | até 1 | mínimo de regime |
| `QUANT_STOP_ATR` | até 10 | distância do stop |
| `QUANT_TRAIL_ATR` | 0 a 10 | 0 desliga |
| `QUANT_VOL_SIZE` | 0, 1 | tamanho por volatilidade |
| `QUANT_FLOW_MIN` | 0 a 1 | filtro de fluxo; 0 desliga |
| `QUANT_DIRECTION` | `both`, `long` | `long` só abre compras |
| `QUANT_MAX_DAILY_LOSS` | até 1000 | perda do dia por ativo |
| `QUANT_MAX_TOTAL_LOSS` | até 100000 | perda do dia somada |

## Preços

Os 20 ativos de cripto do catálogo usam as barras públicas da Binance; os demais usam as velas da própria Kalshi.
O catálogo (`src/quant/live/catalog.json`) é gerado por [`scripts/gen_catalog.py`](../scripts/gen_catalog.py).

## Executores

| Executor | Situação |
|---|---|
| `PaperExecutor` | simulado, sem chave |
| `KalshiPerpsExecutor` | em uso na demo (o aviso "não testado" no topo do arquivo é anterior a esse uso) |
| `BinanceFuturesExecutor` | testado só contra um cliente falso |
| `PolymarketPerpsExecutor` | não testado; não há testnet |
