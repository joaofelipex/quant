# trend_19cripto: o trend_follow em 19 criptos, 1 h

**Veredito: inconclusivo.** Não passa no DSR; roda na demo só para acumular evidência em tempo real.

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
