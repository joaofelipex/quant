# 03 · Macro

## Juros, inflação e política monetária
- Juro real ex-ante: `r ≈ i - E[π]` (exato via Fisher).
- Regra de Taylor: `i = r* + π + 0,5·(π - π*) + 0,5·(hiato do produto)`. Compare com a Selic atual: acima/abaixo sugere postura restritiva/frouxa.
- Curva de juros: nível reflete expectativa de Selic; prêmio de prazo reflete risco fiscal e inflação.
- Surpresa de indicador: `z = (divulgado - consenso) / desvio-padrão histórico das surpresas`.

## Câmbio
- Paridade coberta: `F = S·(1 + i_dom)/(1 + i_ext)`.
- PPP (relativa): câmbio tende a acompanhar o diferencial de inflação no longo prazo.
- Carry trade: ganha o diferencial de juros se a moeda não depreciar o equivalente; risco de reversões bruscas.
- Termos de troca e preços de commodities afetam BRL.

## Atividade
- Crescimento real: `(1 + g_nominal)/(1 + π) - 1`.
- Lei de Okun: relação entre desemprego e hiato do produto.
- Indicadores: PIB, produção industrial, varejo, PMI, desemprego, confiança.

## Regimes
Combine crescimento e inflação em quadrantes para decidir que classe de ativo tende a ir melhor:

| | Inflação sobe | Inflação cai |
|---|---|---|
| **Crescimento sobe** | commodities, ações cíclicas | ações, crédito |
| **Crescimento cai** | juros reais, ouro | títulos longos, defensivas |

É uma heurística, não regra. Valide com dados históricos antes de usar.

## Dados e fontes
- Banco Central: SGS (séries) e Focus (expectativas).
- IBGE (IPCA, PIB), FRED (EUA e global), Tesouro Transparente.

## Armadilhas
- Revisões: dados macro são revisados; use *vintage* (o que se sabia na data), não a série final, em backtest.
- Defasagem de divulgação: PIB só sai semanas depois do período.
