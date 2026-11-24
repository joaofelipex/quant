# runner_eth_1m - a estratégia do runner ao vivo dá lucro?

**Status: REPROVADA. Perde dinheiro em todos os anos testados.**

**O que foi testado:** a estratégia que o `quant.live` roda hoje (`trend_follow`: Donchian + regime ER, sessão de 24 h,
stop de 2 ATR) em ETHUSDT de **1 minuto**, 2023-01 a 2025-10, com custo de 7 bps por lado. O motor tem alvo
(`risk_reward`) e o runner não; por isso as duas pontas: `rr=2` e `rr=50` (na prática só o stop).
Nada foi ajustado: é a configuração que está na VM. Roda com `python estudos/runner_eth_1m/run_check.py`.

| Período | rr | Trades | PnL (USD por 1 ETH) | Profit factor |
|---|---|---|---|---|
| 2023 | 2 | 8 120 | -19 800 | 0,26 |
| 2023 | 50 | 3 475 | -7 885 | 0,47 |
| 2024 | 2 | 6 399 | -27 913 | 0,42 |
| 2024 | 50 | 2 912 | -10 668 | 0,61 |
| 2025 (até out.) | 2 | 5 066 | -21 759 | 0,47 |
| 2025 (até out.) | 50 | 2 408 | -8 785 | 0,64 |

## Leitura
- **Profit factor entre 0,26 e 0,64 nos 3 anos e nas duas variantes**: o resultado não depende de um período.
- O mesmo mecanismo do `eth_ml`: milhares de trades por ano a 14 bps de ida e volta transferem o ganho para a corretora.
  A estratégia veio do WIN em 5 min (PF 0,94 no contrato novo) e foi plugada em ETH 1 min sem nunca ter sido validada.
- **Conclusão:** o runner serve para provar o encanamento (entrada, stop, kill-switch, estado), não para gerar retorno.
  Não deve ir para conta real nem ser lido como evidência de lucro. A única candidata com Sharpe líquido positivo fora da
  amostra é a `tsmom_cripto` (Sharpe 0,80 no hold-out), que **também** não passou na regra do repo (DSR 0,20; alfa t = 0,75)
  e segue em paper.
