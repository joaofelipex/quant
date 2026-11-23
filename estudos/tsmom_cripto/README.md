# tsmom_cripto - tendência diária multi-ativo em cripto

**Status:** desenho pré-registrado em 2026-11-23, escrito ANTES de rodar qualquer resultado. Os números abaixo do
título "Resultado" só existem depois da execução; o desenho acima dele não pode mais ser alterado sem registrar
a mudança e contar a tentativa no DSR.

## Por que esta hipótese
O estudo `eth_ml` mostrou que sinais de horas morrem no custo (7 bps por lado). Tendência diária tem giro baixo
(dezenas de trocas por ano), então o custo pesa pouco. Momentum de série temporal é um dos efeitos mais documentados,
inclusive em cripto, e tem explicação econômica (reação lenta a informação, fluxo de capital em retail, risco
compartilhado de regime). **Risco principal:** em 2020-2025 cripto subiu muito; é fácil confundir *beta de alta* com
habilidade. O estudo mede isso explicitamente.

## Desenho (fixado)
- **Universo:** BTC, ETH, BNB, SOL, XRP, ADA (USDT perpétuos; sinal em preço spot diário; dados `data.binance.vision`).
  Escolhidos por liquidez, não por desempenho. Ativos entram quando têm histórico suficiente.
- **Sinal:** média do sinal do retorno acumulado em **20, 60 e 120 dias** (em [-1, 1]); `long_only` zera o lado vendido.
- **Tamanho:** alvo de volatilidade 20% a.a. dividido pela vol realizada (EWMA 30 d), risco igual entre ativos,
  alavancagem bruta máxima 2×.
- **Execução:** decisão no fechamento de *t*, entrada na abertura de *t+1*, rende até a abertura de *t+2*;
  banda sem-negociação de 3% do capital por ativo.
- **Custos:** 7 bps por lado sobre o giro (taxa taker + slippage) **e funding real** dos perpétuos pago/recebido
  (long paga quando positivo). Mesmo o `long_only` paga funding (conservador: em spot não pagaria).
- **Hold-out:** desenvolvimento 2020-09 a 2023-06; **hold-out 2023-07 a 2025-10, avaliado uma única vez**, depois de
  tudo acima congelado. Como nenhum parâmetro é ajustado, o hold-out serve para checar estabilidade.
- **Variantes olhadas (N_TRIALS):** 2 (long/short, long-only) × 3 conjuntos de janelas {rápido 10/30/60, base 20/60/120,
  lento 60/120/250} = 6 desta família + 24 do `eth_ml` = **30** (conta conservadora no DSR). A variante primária,
  decidida agora, é **base, long/short**. As outras são análise de robustez, não seleção.

## Critérios de aprovação (da regra do repo, aplicados à variante primária no hold-out)
1. Sharpe líquido > 0 e **alfa sobre o beta do mercado cripto** com t > 2 (não basta bater o buy-and-hold).
2. DSR ≥ 0,95 com N_TRIALS = 30.
3. Positivo com custos ×2 e funding incluído.
4. Bootstrap em blocos: P(Sharpe ≤ 0) < 5%.
5. Não depende de um único ativo (leave-one-out) nem de um único ano.

Se falhar em qualquer um, fica em `estudos/` com o resultado negativo escrito.

---

## Resultado (executado em 2026-11-23; tabelas completas em [`reports/resultados.md`](reports/resultados.md))

**Veredito pela regra pré-registrada: REPROVADA** (passa só o critério 3; falham 1, 2, 4 e 5).

| | Dev (2020-09 a 2023-06) | Hold-out (2023-07 a 2025-10) |
|---|---|---|
| Sharpe líquido (primária) | 0,95 | 0,80 |
| Retorno / vol / max DD | 11% / 11% / -14% | 9% / 11% / -16% |
| Cesta cripto equiponderada (Sharpe) | 1,19 | 1,41 |

| Critério (hold-out) | Valor | Passou |
|---|---|---|
| Sharpe > 0 e alfa com t > 2 | Sharpe 0,80; alfa 5,3% a.a., **t = 0,75** | não |
| DSR ≥ 0,95 (N_TRIALS = 30) | **0,20** | não |
| Positivo com custos ×2 | 0,71 (×4: 0,52) | sim |
| P(Sharpe ≤ 0) < 5% (bootstrap em blocos) | **13,6%** (IC 90%: -0,38 a 1,97) | não |
| Positivo sem cada ativo e em todos os anos | todos os ativos sim; **2025: -0,5%** | não |

### Leitura honesta
- **Há sinal consistente, mas sem prova estatística.** Sharpe positivo no desenvolvimento e no hold-out, positivo sem
  qualquer ativo, e robusto a custos (giro de ~11 trocas/ano, custo de 0,8% a.a., funding de -1,7% a.a.). Só não
  há poder estatístico: 2,3 anos de hold-out não separam um Sharpe de 0,8 de sorte (alfa t = 0,75).
- **É um diversificador, não um multiplicador de capital:** beta de 0,04 contra a cesta e retorno de ~10% a.a. com vol
  de 11%. A cesta cripto rendeu ~90% a.a. no período (mercado de alta); a estratégia **não bate buy-and-hold em retorno
  nem em Sharpe**. Ela vale pelo risco baixo (max DD -16% contra -81% da cesta).
- **Sobre as variantes long-only** (Sharpe 1,5 a 1,7): são beta de cripto disfarçado, e escolhê-las agora, depois de ver
  o hold-out, seria seleção posterior. Não foram promovidas.
- **2025 é o primeiro ano ~zero (-0,5%):** as janelas de 20 a 120 dias sofrem em mercado lateral.
- **Tamanho:** a vol realizada (11%) ficou abaixo do alvo (20%) porque o orçamento de risco é dividido igualmente entre 6
  ativos e a banda reduz giro. Alavancar para 20% de vol multiplicaria retorno e drawdown por ~1,8× sem alterar o Sharpe.
  Não foi alterado: o desenho está pré-registrado.

### O que fazer com isso
1. **Não liberar para conta real** (a regra do repo não foi cumprida).
2. **Paper trading a partir de agora** é a única forma de obter dado realmente novo: cada mês acrescenta fora da
   amostra de verdade. Reavaliar com os mesmos critérios após 12 meses.
3. **Runner de paper feito:** `python -m quant.live.portfolio` (ver README da raiz). Começou em 2026-11-23 com 100% em
   caixa e entrou nos pesos-alvo do dia; o relógio dos 12 meses de avaliação conta a partir daí. O paper reproduz o
   backtest (teste `tests/test_portfolio_paper.py`) e deve ser reavaliado com os mesmos 5 critérios.
