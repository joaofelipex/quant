# 01 · Ações

## Modelos de retorno e fatores
- CAPM: `E[R_i] = rf + β_i·(E[R_m] - rf)`.
- Alfa de Jensen: `α = R_i - [rf + β·(R_m - rf)]` (regressão do excesso de retorno no excesso do mercado).
- Fama-French 3 fatores: `R_i - rf = α + β_m·MKT + β_s·SMB + β_v·HML + ε`.
- Fatores clássicos: valor (P/VP, P/L baixos), momentum (12-1), qualidade (ROE, margem), tamanho, baixa volatilidade.
- Momentum 12-1: retorno dos últimos 12 meses excluindo o último mês, ranking cross-section.

## Valuation
- Gordon: `P = D₁ / (k - g)`, exige `k > g`.
- DCF: `V = Σ FCF_t/(1+WACC)^t + VT/(1+WACC)^n`, `VT = FCF_{n+1}/(WACC - g)`.
- WACC: `E/(E+D)·Ke + D/(E+D)·Kd·(1 - IR)`.
- Múltiplos: P/L, P/VP, EV/EBITDA, EV/Receita, Dividend Yield.
- DuPont: `ROE = margem líquida × giro do ativo × alavancagem`.
- Valuation é muito sensível a `g` e `WACC`: sempre mostre uma tabela de sensibilidade.

## Mean reversion e pairs
- Z-score: `z = (x - média_n)/desvio_n`. Sinal contra extremos, só em regime lateral.
- Cointegração (Engle-Granger): regrida `Y = a + b·X + e`; teste ADF nos resíduos.
- Spread de pairs: `S_t = Y_t - b·X_t`. Entrada em `|z| > 2`, saída em `z ≈ 0`.
- Ornstein-Uhlenbeck: `dS = θ(μ - S)dt + σ dW`. Meia-vida: `ln(2)/θ`; na prática, de `ΔS_t = φ·S_{t-1} + ε` temos `meia-vida = -ln(2)/ln(1+φ)`.

## Tendência
- Médias móveis, cruzamentos, rompimentos (Donchian), filtros de regime (ER, ADX).
- Retorno esperado vem de poucos movimentos grandes: a taxa de acerto costuma ser baixa (35-45%).

## Dados necessários
Preço ajustado (dividendos, splits), volume, liquidez média diária, composição do índice (evitar viés de sobrevivência), balanços trimestrais.

## Armadilhas
- Preço não ajustado gera falsos gaps.
- Backtest só com ações que sobreviveram.
- Ignorar liquidez e custos em small caps.
