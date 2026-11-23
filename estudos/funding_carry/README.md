# funding_carry — carry de funding delta-neutro em cripto

**Status: REPROVADA (critério 5, risco de cauda). O carry existe, mas encolheu e o risco que sobra não é pago.**

**Hipótese:** nos perpétuos, quem está comprado paga funding a quem está vendido quando o mercado é otimista. Comprar o
spot e vender o perpétuo na mesma quantidade zera o risco direcional e embolsa o funding. É "arbitragem" só no nome:
sobram risco de base, de funding negativo, de liquidação da perna vendida e de contraparte.

```bash
for s in BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT; do
  python -m quant.data.fetch_binance $s 1d 2020-01 2025-10           # spot
  python -m quant.data.fetch_binance $s 1d 2020-01 2025-10 --perp    # perpétuo
  python -m quant.data.fetch_funding $s 2020-01 2025-10
done
python estudos/funding_carry/run_study.py     # reports/resultados.md e equity.png
```

## Desenho (pré-registrado: fixado antes de calcular qualquer retorno; nada foi reotimizado)

| Item | Valor |
|---|---|
| Universo do veredito | BTC + ETH, capital em partes iguais (os demais pares baixados só como robustez, na grade de `reports/resultados.md`: universo escolhido em 2025 = viés de sobrevivência) |
| Sinal | funding médio dos últimos L dias (até ontem), anualizado, acima de um piso H → liga. Primária: L = 14, H = 5% a.a. |
| Variantes olhadas | L ∈ {7, 14, 30} × H ∈ {0, 5%, 10%} + sempre ligado = 10 × 2 universos → **N_TRIALS = 20** |
| Custo | 20 bps por troca de estado (abrir/fechar as duas pernas: taxas + slippage) |
| Capital | nocional × (1 + margem 20%); margem e caixa rendem zero; margem recomposta todo dia |
| Períodos | dev 2020-01 → 2023-06; hold-out 2023-07 → 2025-10 |
| Critérios (todos) | (1) retorno anual líquido no hold-out > 4% (juro USD de referência, premissa minha); (2) DSR ≥ 0,95; (3) > 0 com custos ×3; (4) bootstrap em blocos P(média ≤ 0) < 5%; (5) zero dias de risco de liquidação com a posição ligada e drawdown do hold-out ≥ −5% |

Código: `src/quant/strategies/funding_carry.py` (9 testes, incluindo ausência de look-ahead no sinal).

## Resultado (BTC + ETH, líquido de custos, sobre o capital)

| | Dev (2020–23/06) | **Hold-out (2023/07–25/10)** |
|---|---|---|
| Variante primária (L14, H5%) | 12,5% a.a. | **5,2% a.a.** |
| Sempre ligado | 14,6% a.a. | 7,5% a.a. |
| Funding bruto médio BTC+ETH | 2020: 22% · 2021: 34% · 2022: 2,5% · 2023: 8% · 2024: 12% · 2025: 5% | |
| Custo da primária (por ano) | −1,9% | −1,5% |
| Retorno com custos ×3 / ×5 | | 2,2% / −0,8% |
| Bootstrap em blocos, IC 90% | | [3,1%; 7,3%] |

Critérios 1 a 4 passam; o **5 falha**.

## Leitura

- **O carry é real, mas encolheu.** O funding bruto caiu de 22–34% a.a. (2020–21) para 5–12% (2023–25). Depois de custos
  e do capital parado na margem, o hold-out rende ~5% (7,5% se nunca desligar), perto do juro em dólar de referência
  (4%, confira a taxa atual). Em reais, o CDI do mesmo período foi ~12,4% a.a. (SGS 12), mas moedas diferentes não se
  comparam sem opinião sobre o câmbio.
- **Os filtros de timing atrapalham.** "Sempre ligado" rende mais que a primária no dev (14,6% contra 12,5%) e no
  hold-out (7,5% contra 5,2%). O filtro fica desligado ~30% do tempo e cada troca custa 20 bps: o funding negativo
  que ele evita não compensa o funding positivo que deixa de receber mais o custo das trocas.
- **O Sharpe e o DSR não servem aqui.** Sharpe de 8 a 14 e DSR = 1,000 saem de uma volatilidade diária de ~0,6%: é
  payoff de vender volatilidade (ganhos pequenos e constantes, perda rara e grande). O teste que importa é o 5.
- **O risco de cauda é o ponto.** Com margem de 20% e a perna vendida ligada, houve **10 dias** em que a máxima do
  perpétuo superou a margem livre (9 pela máxima do spot, que aproxima o preço de marcação usado na liquidação): altas
  reais de 20 a 31% em 24 h (13/03/2020, 03/01/2021, 24/05/2021, 20/05/2024...). Margem de 35% zera os dias pelo
  proxy do spot, ao custo de cair de 5,2% para 4,6% a.a., já na casa do juro de referência.
- **A máxima do perpétuo tem mechas anômalas** (ETH 13/03/2020: +202% no perpétuo contra +30% no spot); não removi, por
  isso o critério pré-registrado fica como está e o proxy do spot aparece ao lado.

## O que NÃO está modelado (e pesa)

- **Contraparte**: tudo fica numa exchange (spot + perpétuo). Falência ou congelamento (FTX, 2022) não aparece em
  nenhum backtest de preços.
- **Auto-deleveraging, limites de saque/transferência e mudanças de regra** da exchange.
- **Margem unificada (portfolio margin)**: com o spot como colateral o risco de liquidação cai muito; exige conta e
  condições específicas.
- **Rendimento do caixa/margem parados** (aqui é zero) e **impostos**.
- Funding de 00:00 liquida na hora da troca; o modelo ignora esse detalhe.
- Dados diários: nada de recomposição intradiária de margem.

## Próximos passos (só se o carry voltar a justificar o risco)

1. **Cash-and-carry com futuros trimestrais**: a base é conhecida na entrada e converge no vencimento, sem risco de
   funding virar negativo. Precisa dos dados dos futuros datados.
2. **Arbitragem de funding entre exchanges** (comprado onde o funding é menor, vendido onde é maior): exige dados e
   contas em mais de uma exchange; o risco de contraparte dobra.
3. **Prever o regime de funding** (alavancagem agregada, open interest) em vez de olhar só o funding passado.
4. Rodar o paper do carry só depois de passar no roteiro de testnet (`docs/roteiro_testnet.md`).

Isto é pesquisa, não recomendação de investimento.
