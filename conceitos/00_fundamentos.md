# 00 · Fundamentos

## Retornos
- Simples: `r_t = P_t / P_{t-1} - 1`
- Log: `R_t = ln(P_t / P_{t-1})` — soma ao longo do tempo (`R_total = ΣR_t`).
- Acumulado: `Π(1 + r_t) - 1`. CAGR: `(P_fim/P_ini)^(252/n_dias) - 1`.
- Com alavancagem ou dividendos, use retorno total (ajustado).

## Risco
- Volatilidade: `σ = desvio-padrão(R_t)`; anualizada `σ_a = σ_diária × √252`.
- EWMA (RiskMetrics): `σ²_t = λ·σ²_{t-1} + (1-λ)·R²_{t-1}`, `λ ≈ 0,94` (diário).
- ATR (Wilder): média de `TR = max(H-L, |H-C_{-1}|, |L-C_{-1}|)`. Mede amplitude, não direção.
- Drawdown: `DD_t = Equity_t / max(Equity_{≤t}) - 1`; Max DD = mínimo da série.
- Assimetria (skew) e curtose (kurtosis): retornos de mercado têm caudas gordas; normal subestima risco.
- Correlação: `ρ = Cov(x,y)/(σx·σy)`. Instável em crises: tende a subir.
- Beta: `β = Cov(r_ativo, r_mercado) / Var(r_mercado)`.

## VaR e ES
- VaR paramétrico (normal): `VaR_α = -(μ + z_α·σ)·Valor`, `z_95 = -1,645`, `z_99 = -2,326`.
- VaR histórico: percentil `α` da distribuição empírica de retornos.
- Expected Shortfall: média das perdas além do VaR. Mais informativo que o VaR sozinho.

## Desempenho
- Sharpe: `(μ - rf)/σ`, anualizado × `√252`.
- Sortino: usa só o desvio dos retornos negativos (downside deviation).
- Calmar: `CAGR / |Max DD|`.
- Profit factor: `lucro bruto / |prejuízo bruto|`.
- Expectância por trade: `E = p·W - (1-p)·L` (W e L em unidade monetária ou em R).
- Payoff (R:R) e taxa de acerto precisam ser lidos juntos: `breakeven p* = L/(W+L)`.

## Dimensionamento de posição
- Risco fixo por trade: `contratos = (capital × risco%) / (distância do stop × valor do ponto)`.
- Kelly (binário): `f* = p - (1-p)/b`, com `b = W/L`.
- Kelly contínuo (aprox.): `f* ≈ μ/σ²`. Na prática use **½ Kelly ou menos**: o erro de estimar μ é grande.
- Volatility targeting: `peso = σ_alvo / σ_estimada`.

## Séries temporais
- Estacionariedade: teste ADF (rejeitar raiz unitária). Preço raramente é estacionário; retorno costuma ser.
- Autocorrelação (ACF/PACF): detecta momentum (positiva) ou reversão (negativa).
- Expoente de Hurst `H`: `>0,5` persistente (tendência), `<0,5` reverte, `≈0,5` passeio aleatório.
- Efficiency Ratio de Kaufman: `|C_t - C_{t-n}| / Σ|C_i - C_{i-1}|`, de 0 (ruído) a 1 (tendência). Já usado no `profitpro`.

## Armadilhas
- Anualizar retorno intradiário sem separar overnight.
- Tratar Sharpe de poucos trades como estatística confiável (ver `06_validacao_backtest.md`).
