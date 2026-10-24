# 04 · Derivativos

## Futuros
- Preço teórico: `F = S·e^{(r - q)·T}` (q = dividendos ou convenience yield).
- Basis: `F - S`. Converge a zero no vencimento.
- Contango (F > S) / backwardation (F < S).
- Rolagem: contratos expiram. Séries contínuas (`WIN$`) emendam contratos e podem ter gap; defina a regra (volume ou data).
- Ponto e tick: WIN 1 ponto = R$ 0,20, tick = 5 pontos; WDO 1 ponto = R$ 10 por contrato, tick = 0,5.

## DI futuro (B3)
- `PU = 100.000 / (1 + taxa)^(du/252)`.
- Sensibilidade (DV01) cresce com o prazo: contratos longos movem mais por 1 bp.
- Aposta em Selic futura: comprar taxa lucra se os juros sobem.

## Opções (Black-Scholes, europeia)
- `d1 = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)`, `d2 = d1 - σ·√T`.
- Call: `C = S·N(d1) - K·e^{-rT}·N(d2)`. Put: `P = K·e^{-rT}·N(-d2) - S·N(-d1)`.
- Paridade put-call: `C - P = S - K·e^{-rT}`.
- Gregas: Delta `∂V/∂S`, Gamma `∂²V/∂S²`, Vega `∂V/∂σ`, Theta `∂V/∂t`, Rho `∂V/∂r`.
- Volatilidade implícita: o `σ` que iguala o modelo ao preço de mercado; tem *smile/skew*.
- Prêmio de risco de volatilidade: vol implícita tende a superar a realizada, em média.
- Hedge delta: `posição no ativo = -Delta × quantidade de opções`.

## Estratégias comuns
- Travas, straddle/strangle, borboleta, calendário, venda coberta. Calcule sempre payoff, ponto de equilíbrio e perda máxima.

## Dados necessários
Cadeia de opções (strikes, vencimentos, bid/ask), vol implícita histórica, DI e dividendos para `r` e `q`.

## Armadilhas
- Black-Scholes assume vol constante e saltos ausentes: subestima caudas.
- Opções americanas (ações no Brasil costumam ser) exigem ajuste para exercício antecipado.
- Liquidez de strikes distantes é baixa: bid/ask domina o resultado.
