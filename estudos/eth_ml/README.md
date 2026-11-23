# eth_ml - ML prevê a direção do ETH em 1 h?

**Hipótese:** features causais de preço, volatilidade, volume e fluxo (fração de volume agressor comprador) contêm
informação sobre a direção dos próximos 4 h, e um modelo simples (regressão logística ou gradient boosting) a extrai
depois de custos.

**Desenho** (fixado antes de ver o resultado; detalhes no docstring de [`run_study.py`](run_study.py)):
ETHUSDT spot 1 h, 2021-01 a 2025-10 · walk-forward 540 d treino / 30 d teste com purga · só a série OOS é avaliada ·
custo 5 bps taxa + 2 bps slippage por lado · 7 variantes olhadas (2 modelos × 3 limiares + momentum), usadas no DSR.

```bash
python -m quant.data.fetch_binance ETHUSDT 1h 2021-01 2025-10
python estudos/eth_ml/run_study.py        # grava reports/resultados.md e reports/equity.png
```

## Resultado (OOS 2022-06 a 2025-10, 3,3 anos)

| | Sharpe bruto | Sharpe líquido (custo ×1) | ×2 | DSR |
|---|---|---|---|---|
| buy and hold | 0,97 | 0,97 | 0,97 | - |
| momentum 24 h (baseline) | -0,72 | -2,64 | -4,54 | 0,0 |
| logit (melhor limiar 0,05) | 1,36 | **-1,75** | -4,82 | 0,0 |
| gbm (melhor limiar 0,00) | 1,91 | **-2,68** | -7,18 | 0,0 |

AUC fora da amostra: logit 0,544 · gbm 0,551. Tabela completa em [`reports/resultados.md`](reports/resultados.md).

## Leitura

- **Todas as variantes perdem dinheiro depois de custos.** Nenhuma passa na regra do repo (DSR ≥ 0,95).
- O modelo parece ter *alguma* informação (AUC ~0,55, Sharpe bruto acima de 1), mas o giro é de **~2 000 a 4 000
  mudanças de posição por ano**: reavaliar a cada hora e trocar de lado a cada flutuação de probabilidade transfere
  todo o ganho para a corretora.
- Esse AUC é alto para 1 h em ETH, então foi testado em [`sanity.py`](sanity.py) (seção abaixo).

## Sanidade do sinal (`sanity.py`)

| Teste | Resultado | Leitura |
|---|---|---|
| Rótulos embaralhados no treino | AUC 0,500 (logit) e 0,498 (gbm) | pipeline não vaza: sem informação, dá 0,5 |
| Viés de alta | 50,7% dos rótulos positivos; acurácia 53-54% | não é só "ETH subiu no período" |
| Features atrasadas 1 / 2 / 6 / 24 barras | gbm 0,539 / 0,525 / 0,518 / 0,507 | sinal de curto prazo: some em ~1 dia |
| Score ingênuo sem modelo | r24: 0,458 · dist_ema24: 0,463 · r4: 0,470 | AUC < 0,5 = **reversão à média**: retorno passado alto prevê queda |
| AUC por ano | 0,54-0,56 em 2022, 2023, 2024 e 2025 | estável, não depende de um regime |

**Conclusão:** não achei vazamento. O que o modelo captura é essencialmente **reversão à média de curtíssimo prazo**
(quanto mais o ETH subiu nas últimas horas, maior a chance de devolver nas próximas 4 h). É um efeito pequeno e
consistente, mas o ganho por trade fica abaixo do custo de 14 bps de ida e volta. Não é edge operável com ordens a
mercado; seria preciso custo muito menor (ordens limitadas) ou movimentos maiores por trade.

## Rótulo de magnitude (`run_magnitude.py`)

Rótulo de 3 classes (alta > m, queda < -m, meio) e posição só quando P(alta) - P(queda) passa de um limiar d.
8 variantes novas (2 modelos × m ∈ {0,5%, 1,0%} × d ∈ {0,05, 0,10}); DSR usa N_TRIALS = 15 (as 7 antigas + 8).
Tabela completa em [`reports/resultados_magnitude.md`](reports/resultados_magnitude.md).

| Variante | Sharpe bruto | Sharpe líquido | ×2 custos | Giro/ano | DSR |
|---|---|---|---|---|---|
| logit m=1,0% d=0,10 (melhor) | 1,13 | **0,46** | -0,21 | 215 | 0,18 |
| logit m=0,5% d=0,10 | 1,60 | 0,09 | -1,41 | 670 | 0,06 |
| gbm (todas as 4) | 0,7 a 2,1 | -1,6 a -2,6 | < -3,9 | 1 100 a 3 500 | 0,00 |

- Exigir movimento maior que o custo **reduziu o giro de ~4 000 para ~215 trocas/ano** e levou a melhor variante de
  Sharpe líquido -2,7 para +0,46. A direção correta é filtrar trades, como suspeitávamos.
- **Ainda não é edge:** DSR 0,18 (< 0,95), a melhor variante é a única positiva entre 8 (selecionada ex-post), fica
  posicionada só 3% do tempo (poucos trades, intervalo de confiança largo) e vira negativa com custos ×2.
- A logística supera o gradient boosting em todas as configurações: o modelo flexível sobreajusta o ruído.

### Replicação em BTC e SOL

`python estudos/eth_ml/run_magnitude.py BTCUSDT` (e `SOLUSDT`). Mesmo período, mesmos parâmetros, nada reotimizado;
a variante pré-especificada para a réplica foi a melhor do ETH (logit, m = 1,0%, d = 0,10).

| Ativo | Sharpe bruto | Sharpe líquido | ×2 custos | Giro/ano | Tempo posicionado |
|---|---|---|---|---|---|
| ETH (amostra de seleção) | 1,13 | +0,46 | -0,21 | 215 | 3% |
| BTC | 0,47 | **-0,17** | -0,81 | 129 | 2% |
| SOL | 0,91 | +0,26 | -0,38 | 383 | 5% |

- **Não replicou de forma limpa:** BTC fica negativo, SOL é positivo mas pequeno (DSR 0,10), e nos três a variante
  vira negativa com custos ×2. O gradient boosting perde nos três ativos.
- O padrão que se repete é o **Sharpe bruto positivo e a perda para o custo**: existe uma reversão de curto prazo, mas
  ela é do tamanho do custo de ordens a mercado.

**Leitura:** há indício fraco de que filtrar por magnitude ajuda, mas nada que justifique operar. A réplica em BTC e SOL
(acima) não confirmou: o efeito é grande demais para ser ruído, mas pequeno demais para pagar o custo.

## Ordens limitadas (`run_limit.py`)

Mesmo sinal fixo (logit, m = 1,0%, d = 0,10), simulado trade a trade: entrada com ordem limitada em `close[t]`,
executada só se a mínima/máxima da barra seguinte *ultrapassar* o preço (`through`), saída a mercado ou limitada.
Pessimista de propósito: barras OHLC não têm fila, então só é executado quando o preço andou contra nós (seleção
adversa). 8 variantes (maker 2 ou 5 bps × through 0 ou 2 bps × saída), N_TRIALS = 24. Tabelas em
`reports/resultados_limite*.md`.

| Ativo | Referência a mercado | Limite (maker 2, through 0) | Limite (maker 2, through 2) | Limite (maker 5, through 2) |
|---|---|---|---|---|
| ETH | +3,3 bps/trade | +8,3 a +12,1 | +2,2 a +4,0 | -0,8 a -1,9 |
| BTC | -0,1 | +3,9 a +6,7 | +0,2 a +0,8 | -2,8 a -5,0 |
| SOL | -1,8 | +2,5 a +3,0 | +0,1 a +1,3 | -1,7 a -5,8 |

(líquido de custos, por trade; 200 a 550 trades por ativo)

- **Nenhuma variante é distinguível de zero:** t-stat máximo 0,87 (ETH), DSR por trade ≤ 0,14.
- Ordens limitadas ajudam (cortam ~5 a 10 bps por trade frente ao mercado), mas o ganho depende de premissas que
  OHLC não consegue validar: com taxa maker de 5 bps ou exigência de ultrapassar o preço em 2 bps, o resultado cai
  a zero ou fica negativo.
- Para saber se o maker funciona de verdade seria preciso dado de book/trades (ou paper trading na exchange medindo
  a taxa real de execução e a seleção adversa).

**Conclusão do estudo `eth_ml`:** existe uma reversão de curto prazo pequena e real (AUC ~0,55, sem vazamento), mas
ela não paga o custo em ETH, BTC ou SOL com as premissas conservadoras. Resultado negativo registrado.

## Próximos passos (em ordem)

1. ~~Sanidade do sinal~~ (feito, ver acima): sem vazamento; o sinal é reversão de curto prazo.
2. **Reduzir giro** (parcialmente atacado pela magnitude): histerese entre limiares de entrada e saída, posição
   dimensionada pela confiança.
3. ~~Rótulo de magnitude~~ (feito, ver acima): melhora, mas sem passar nos critérios.
   Replicado em BTC/SOL: não confirmou.
4. Só então: meta-labeling sobre uma regra simples e previsão de volatilidade para dimensionar a posição.

Resultado negativo registrado de propósito: a regra do repo é tentar derrubar a estratégia, não confirmá-la.
