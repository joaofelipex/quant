# xsmom_cripto - momentum de corte transversal, neutro em dólar, em cripto

**Status:** desenho pré-registrado em 2026-11-24, escrito ANTES de rodar qualquer resultado. Os números só existem
depois da execução; o desenho abaixo não pode mais ser alterado sem registrar a mudança e contar a tentativa no DSR.

## Por que esta hipótese
A `tsmom_cripto` (tendência de série temporal) tem beta de 0,04, Sharpe líquido de 0,80 no hold-out, mas sem poder
estatístico (alfa t = 0,75). Esta hipótese é **outra fonte de retorno**: comprar os ativos que mais subiram e vender os
que menos subiram *entre si*, na mesma semana. Fica neutra em dólar, então não depende de o mercado cripto subir (o
risco que a `tsmom_cripto` deixou aberto). Tem lógica econômica: reação lenta a informação e fluxo de varejo
concentrado nos vencedores; mas em cripto o efeito de corte transversal é menos documentado que o de série temporal,
e o universo é pequeno (6 ativos), então o risco de não existir sinal é alto.

## Desenho (fixado)
- **Universo:** BTC, ETH, BNB, SOL, XRP, ADA (perpétuos USDT; preços diários; dados já baixados). O mesmo da `tsmom_cripto`.
- **Sinal:** retorno acumulado de **60 dias** no fechamento de *t*; ranking entre os ativos com histórico.
- **Carteira:** a cada **7 dias** (segunda-feira) compra os **2 melhores** e vende os **2 piores**; pesos inversamente
  proporcionais à vol realizada (EWMA 30 d) dentro de cada perna; **perna comprada soma +0,5 e a vendida soma -0,5**
  (bruto 1,0, líquido 0). Entre rebalanceamentos os pesos ficam parados (sem rebalancear por deriva).
- **Execução e custos:** igual à `tsmom_cripto`: decisão no fechamento de *t*, entrada na abertura de *t+1*, 7 bps por lado
  sobre o giro e **funding real** (perna vendida recebe quando positivo).
- **Hold-out:** desenvolvimento 2020-09 a 2023-06; **hold-out 2023-07 a 2025-10, avaliado uma única vez**.
- **Variantes olhadas (N_TRIALS):** primária = janela 60. Robustez (não seleção): janelas 30 e 90. Total **3** desta família
  + 30 já contadas (`eth_ml` + `tsmom_cripto`) = **33** no DSR.

## Critérios de aprovação (os mesmos da regra do repo, na variante primária, no hold-out)
1. Sharpe líquido > 0 e **alfa sobre a cesta cripto** com t > 2.
2. DSR ≥ 0,95 com N_TRIALS = 33.
3. Positivo com custos ×2 e funding incluído.
4. Bootstrap em blocos: P(Sharpe ≤ 0) < 5%.
5. Positivo sem cada ativo (leave-one-out) e em todos os anos.

Se falhar em qualquer um, fica em `estudos/` com o resultado negativo escrito.

---

## Resultado (executado em 2026-11-24; tabelas completas em [`reports/resultados.md`](reports/resultados.md))

**Veredito pela regra pré-registrada: REPROVADA** (passa os critérios 3 e 5; falham 1, 2 e 4).

| | Dev (2020-09 a 2023-06) | Hold-out (2023-07 a 2025-10) |
|---|---|---|
| Sharpe líquido (lb60, primária) | **-0,33** | 1,04 |
| Retorno / vol / max DD | -12,6% / 39% / -59% | 28,7% / 28% / -23% |

- Alfa no hold-out 23,8% a.a., **t = 1,41**; DSR **0,29**; P(Sharpe ≤ 0) = 5,6% (limite 5%).
- **Não é sinal estável:** o Sharpe foi negativo em 2021 e 2022 e positivo só de 2023 em diante; com janela de 30 dias o
  hold-out cai para 0,15 e com 90 dias para 0,56. O Sharpe de 1,04 do hold-out vem de uma única janela de lookback em
  um único regime, depois de um desenvolvimento perdedor: é o padrão típico de ruído, não de borda.
- **Decisão:** não promovida, não vai para paper. Escolhê-la agora por causa do hold-out seria seleção posterior.
