# trend_eth_tf - o `trend_follow` do runner funciona em timeframe maior?

**Status:** desenho pré-registrado em 2026-11-24, escrito ANTES de rodar. Não pode ser alterado sem registrar a mudança.

## Por que esta hipótese
O estudo `runner_eth_1m` mostrou que o `trend_follow` perde em ETH 1 min porque faz milhares de trades por ano a 14 bps de
ida e volta. Se o problema é o custo por trade contra o tamanho do movimento, em timeframe maior (poucas centenas de
trades, movimento médio maior) o mesmo código pode deixar de perder. Isto é um **teste de triagem**, não uma estratégia
nova: nenhum parâmetro do `trend_follow` é alterado (EMA 9/21, Donchian 20, ER 20, stop 2 ATR, alvo 50 ATR).

## Desenho (fixado)
- **Dados:** ETHUSDT 1 min (já baixado) reamostrado para o timeframe; custo 7 bps por lado (taxa fixa por trade pelo preço médio).
- **Variante primária:** **1 h**. Robustez (não seleção): **15 min** e **4 h**.
- **Períodos:** desenvolvimento 2023-01 a 2024-06; **hold-out 2024-07 a 2025-10, avaliado uma única vez**.
- **N_TRIALS:** 30 já contadas + `runner_eth_1m` (2) + `xsmom_cripto` (3) + 3 desta família = **38** no DSR.
- **Limitação conhecida do motor:** ele fecha a posição na virada do dia (`overnight`), o que **subestima** uma estratégia de
  tendência de vários dias. É uma triagem conservadora para o 1 h e para o 4 h; um resultado negativo aqui não descarta
  tendência multi-dia (esta é a `tsmom_cripto`).

## Critérios (variante primária, hold-out)
1. Profit factor > 1,2 e t-stat dos trades > 2.
2. DSR ≥ 0,95 com N_TRIALS = 38.
3. PF > 1 com custo ×2.
4. Positivo em ao menos 2 dos 3 trimestres do hold-out com ≥ 20 trades.

Se falhar em qualquer um, fica em `estudos/` com o resultado negativo escrito.

---

## Resultado (executado em 2026-11-24; tabelas em [`reports/resultados.md`](reports/resultados.md))

**Veredito pela regra pré-registrada: REPROVADA** (passa só o critério 4; falham 1, 2 e 3).

| TF | Dev: trades / PF / t | Hold-out: trades / PF / t |
|---|---|---|
| 15 min | 399 / 0,72 / -2,27 | 358 / 0,94 / -0,40 |
| **1 h (primária)** | 136 / 0,73 / -1,30 | 141 / **1,07** / 0,30 |
| 4 h | 42 / 0,52 / -1,38 | 49 / 0,60 / -1,29 |

- 1 h no hold-out: PF 1,07 e t = 0,30 (nada distinguível de zero); **DSR 0,03**; com custo ×2 o PF cai para 0,93.
- Nenhum timeframe tem PF > 1 no desenvolvimento. Subir o timeframe reduziu o custo (menos trades), mas o `trend_follow` não
  tem borda em ETH: a falha não era só o custo.
- O critério 4 passou por 2 trimestres positivos entre 6 (2024Q3 e 2025Q3, este com +1148 de uma única janela); o texto do
  README dizia "2 dos 3" por engano de redação (o hold-out tem 6 trimestres) e o script aplicou "ao menos 2". Mesmo
  assim, não muda o veredito.
- **Conclusão:** o `trend_follow` do WIN não é a estratégia certa para o runner de ETH em nenhum dos timeframes testados.
  Trocar de timeframe não melhora a precisão do sinal. A única linha com Sharpe líquido positivo fora da amostra
  continua sendo a `tsmom_cripto` (tendência diária multi-ativo), em paper.
