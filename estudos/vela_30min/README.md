# Prever a próxima vela de 30 min (BTC e ETH)

**Veredito: há um sinal pequeno, menor que o custo. Reprovada para operar sozinha.**

Código e desenho em [`testar.py`](testar.py): velas de 1 min da Binance (01/2023 a 09/2026) agregadas em 30 min;
features de preço, formato da vela, volatilidade, volume, negócios, agressão compradora, hora e o outro ativo;
treino 2023-24, limiar escolhido em 2025, prova em 2026.

## Prova (2026)

| Ativo | Movimento médio em 30 min | Melhor AUC | Acerto | Ganho bruto por operação (melhor caso sem custo) |
|---|---|---|---|---|
| BTC | 21,2 bps | 0,531 | 52,3% | 1,1 bps |
| ETH | 26,9 bps | 0,534 | 52,2% | 0,2 bps |

- Com custo de 4 bps ou de 30 bps por ida e volta, todas as variantes perderam em 2025 e em 2026.
- Seguir a última vela acerta menos da metade (48,1%); ir contra ela acerta cerca de 52%.
- Coerente com [`eth_ml`](../eth_ml/README.md): existe informação, e o giro entrega o ganho à corretora.

## Limites

Preços spot da Binance, não da Kalshi demo. Só BTC e ETH, só ordens que pagam a taxa de quem agride. Sem livro de
ofertas histórico. A prova de 2026 já foi olhada: ajustar o modelo em cima dela a invalida.

## Reproduzir

```
python estudos/vela_30min/testar.py
```

## Metais, índices e câmbio (Kalshi demo, [`kalshi.py`](kalshi.py))

**Veredito: reprovada nas três classes.** Compra no ask, venda no bid, taxa da classe por lado; prova nos 25% finais.

| Classe | Ativos | Melhor AUC | Ganho no preço médio | Spread mediano | Líquido executável por operação |
|---|---|---|---|---|---|
| Metais | 6 | 0,522 | 0,6 bps | 6,8 bps | -9,8 a -10,7 bps |
| Índices | 3 | 0,495 | 2,0 bps | 29,6 bps | -24,3 a -28,3 bps |
| Câmbio | 3 | 0,699 | 3,9 bps | 5,9 bps | -6,5 a -8,7 bps |

Valores da prova. Os melhores números de cada coluna podem vir de modelos diferentes. Histórico curto (julho ou
setembro a novembro de 2026), preços da demo e nada sobre execução com ordem parada no livro.
