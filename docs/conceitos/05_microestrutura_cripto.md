# 05 · Microestrutura e cripto

## Preço e liquidez
- VWAP: `Σ(P_i·V_i) / ΣV_i`. Referência de execução; reverte ao VWAP no intradiário é comum.
- Spread: `ask - bid`. Custo implícito por lado ≈ metade do spread.
- Profundidade do book: volume em cada nível; o preço "desliza" quando você consome níveis.
- Impacto de mercado (raiz quadrada): `custo ≈ Y·σ·√(Q/V_dia)`, com `Q` ordem e `V` volume diário.
- Slippage: diferença entre preço esperado e executado; modele em ticks e em função da vol.

## Fluxo de ordens
- Order Flow Imbalance: `OFI = (volume comprador - volume vendedor) / volume total`.
- CVD (delta acumulado): soma contínua do delta agressor.
- Imbalance no topo do book: `(bid_vol - ask_vol)/(bid_vol + ask_vol)`; sinal de curto prazo.
- Em dados sem lado agressor, estime por regra de tick ou Lee-Ready.

## Cripto
- Funding rate (perpétuos): pago entre longs e shorts a cada 8h (ou 1h, conforme corretora). Funding alto e positivo indica excesso de alavancagem comprada.
- Basis: `(F - S)/S` anualizado; base do *cash-and-carry*.
- Open interest: sobe com preço = posições novas; cai com preço subindo = saída de vendidos.
- Liquidações: cascatas de stop em alavancagem geram movimentos rápidos.
- Funcionamento 24/7: anualize por 365 e trate sessões como arbitrárias.

## Custos
- Taxas maker/taker, funding, spread, slippage. Em estratégias de alta frequência, custo decide o resultado.
- Regra prática: o edge bruto por trade precisa superar o custo total com margem (ex.: 2-3×).

## Dados necessários
Trades (tick), book L2 (quando disponível), funding, open interest, liquidações. Binance publica trades e klines em `data.binance.vision`.

## Armadilhas
- Candle de 1 minuto esconde a ordem dos eventos dentro do candle (stop e alvo no mesmo candle: no engine atual assume o pior caso).
- Fuso horário e candle fechado vs. em formação (look-ahead).
