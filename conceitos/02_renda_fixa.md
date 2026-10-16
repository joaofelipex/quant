# 02 · Renda fixa

## Valor presente e yield
- Preço: `P = Σ CF_t/(1+y)^t`. Yield (YTM) é o `y` que iguala o preço de mercado.
- Taxa efetiva anual -> mensal: `(1+i_a)^(1/12) - 1`. Base 252: `(1+i)^(du/252)`.
- Fisher: `(1 + nominal) = (1 + real)·(1 + inflação)`. Inflação implícita (breakeven) ≈ prefixada vs. IPCA+ no mesmo prazo: `(1+pré)/(1+real) - 1`.

## Sensibilidade a juros
- Macaulay: `D = Σ t·PV(CF_t) / P`.
- Duration modificada: `D* = D / (1+y)`.
- `ΔP/P ≈ -D*·Δy + ½·C·(Δy)²` (C = convexidade).
- DV01: variação em R$ para 1 bp: `DV01 ≈ D*·P·0,0001`.
- Quanto maior a duration, maior a perda quando os juros sobem.

## Curva de juros
- Taxa a termo: `(1 + f_{1,2}) = (1+y₂)² / (1+y₁)` (anos).
- Inclinação: `y(10a) - y(2a)`; invertida costuma preceder desaceleração.
- Carry e roll-down: ganho por manter o título + ganho por "descer" a curva se ela for inclinada.
- Fatores da curva (PCA): nível, inclinação, curvatura; explicam grande parte da variação.
- Nelson-Siegel: ajusta a curva com 4 parâmetros, útil para interpolar prazos sem cotação.

## Brasil
- **Selic / CDI**: CDI ≈ Selic - 0,10 p.p.
- **DI futuro (B3)**: PU = `100.000 / (1 + taxa)^(du/252)`. Cotado em taxa. Ver `04_derivativos.md`.
- **Tesouro Prefixado (LTN)**: `PU = 1000 / (1 + taxa)^(du/252)`.
- **Tesouro IPCA+ (NTN-B)**: valor corrigido pelo IPCA, mais cupom real semestral; marcação a mercado muda com a taxa real.
- **Tesouro Selic (LFT)**: duration curta, risco de marcação baixo.
- Tributação regressiva (22,5% a 15%) e isenções (LCI/LCA, debêntures incentivadas) alteram a comparação líquida: sempre compare **taxas líquidas**.

## Crédito
- Spread de crédito: `y_corp - y_gov` no mesmo prazo.
- Perda esperada: `PD × LGD × EAD`.
- Equivalência de isento: `taxa bruta equivalente = taxa isenta / (1 - alíquota)`.

## Dados necessários
Curva DI/pré e IPCA+ (ANBIMA/B3), preços e taxas do Tesouro, Selic e CDI (Banco Central/SGS), IPCA (IBGE).

## Armadilhas
- Comparar taxas bruta vs. líquida, ou 252 vs. 360 dias, sem converter.
- Esquecer marcação a mercado de títulos longos antes do vencimento.
