# trend_19cripto: o trend_follow em 19 criptos, 1 h

**Veredito: inconclusivo.** Não passa no DSR; roda na demo só para acumular evidência em tempo real. Com o custo real
da Kalshi (abaixo), só a base (ER 0,5, sem trailing) fica positiva; é ela que roda na demo desde 27/11/2026, sem o
filtro de fluxo.

- Universo: 19 criptos da Binance (sem HYPE, pouca história), barras de 1 h, 2024-11-25 a 2026-11-25, custo 10 bps ida e volta.
- Treino = 1º ano, teste = 2º ano (buy & hold igual-peso: −42%).
- `tune.py`: 48 variantes (timeframe 1 h/4 h, ER 0,4/0,5/0,6, stop 2/3 ATR, trailing 0/3, tamanho por volatilidade).
- `dsr.py`: PSR e DSR sobre o retorno diário do portfólio igual-peso no teste.

| Config | Teste | PSR (SR>0) | DSR, 16 tentativas | DSR, 64 | DSR, 100 |
|---|---|---|---|---|---|
| base (ER 0,5, stop 2) | +38%, Sharpe 1,45 | 0,97 | 0,33 | 0,13 | 0,09 |
| final (+ trailing 3, tamanho por vol.) | +22%, Sharpe 1,73 | 0,98 | 0,47 | 0,22 | 0,17 |

Com 64 tentativas o Sharpe que o acaso produz sozinho é ~2,4 (anual), acima do observado: não dá para separar do acaso de seleção.
O DSR por trade (0,4 a 0,96) superestima: trades de moedas correlacionadas não são independentes; vale o diário.
Fragilidades: 2 anos só; 4 h perde no treino e ganha no teste (depende do regime); as variantes finais foram escolhidas olhando o teste;
o estudo `trend_eth_tf` já reprovou a mesma família em ETH. Reabrir só com mais histórico ou dados novos (a demo em tempo real).

## Custo real da Kalshi ([`custo_real.py`](custo_real.py), 27/11/2026)

A Kalshi cobra 12 bps por lado a mercado e o spread mediano das criptos na demo é ~10 bps: ~35 bps ida e volta, não 10.
Com esse custo e o funding da Binance (2,2% ao ano para um comprado parado), de 2024-11-25 a 2026-10-31, canal 55,
stop 2 ATR e tamanho por volatilidade:

| Config | Trades | Por trade: bruto / custo / funding (bps) | 1º ano | 2º ano | Sharpe e DD no 2º ano |
|---|---|---|---|---|---|
| antiga, a que rodava na demo (ER 0,4, trailing 3) | 3.661 | +25,6 / −32,9 / −0,9 | −2,9% | −12,7% | −0,83 / −30% |
| atual (ER 0,5, sem trailing) | 1.597 | +186,4 / −33,4 / −3,1 | +105,1% | +20,9% | 0,86 / −25% |

- O funding tira ~1 ponto por ano. Só comprado: +115% / +14%; só vendido: −10% / +7%. Ficam os dois lados.
- Na conta demo o funding quase não aparece: 6 cobranças em 12 dias, US$ 0,01 no total (registros às 05h e 21h UTC).

## Filtro de fluxo ([`fluxo_demo.py`](fluxo_demo.py))

Ligado na demo em 25/11 (`QUANT_FLOW_MIN=0,1`) sem estudo: o robô só entra se o desequilíbrio do livro em 1% do preço
(`imb_100`) apoiar o lado do sinal. Nas fotos de 1 min de 25 a 27/11 (2,3 dias, 19 criptos):

- Libera compra 30% do tempo e venda 16%. DOGE e UNI quase nunca (1%); BTC vendido, 9%. O lado do livro muda por
  ativo (BTC pende para a compra, SOL para a venda) e é o livro da demo, não o do mercado real.
- Acerta o retorno de 15 min (+9,5 bps, t 7,1), menos que o spread. No prazo do robô, não: 1 h +4,9 bps (t 1,7),
  4 h +26,9 (t 0,8), 12 h −26,1 (t −0,1).
- Barrou 11 das 14 entradas do robô desde que foi ligado.

Simulado como uma porta aleatória com essas taxas por ativo e lado (200 sorteios, configuração atual): 719 trades em
vez de 1.597 e retorno total mediano de +68% em vez de +126% (10% piores: +13%). Sem sinal no prazo do robô, o filtro
corta cerca de metade do ganho esperado. Desligado na demo em 27/11/2026 (`QUANT_FLOW_MIN=0`).

## Reproduzir

```
python -m quant.data.fetch_binance <MOEDA>USDT 1h 2024-11 2026-10   # para dados/raw/binance/h1_19/
python -m quant.data.fetch_funding <MOEDA>USDT 2024-10 2026-10      # dados/raw/binance/<MOEDA>USDT_funding.csv
cd estudos/trend_19cripto && python custo_real.py
```

`fluxo_demo.py` roda na VM, sobre as fotos do gravador de fluxo (instruções no próprio arquivo).
