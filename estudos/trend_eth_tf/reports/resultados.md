# trend_eth_tf - resultados

## Veredito: **REPROVADA**
- [ ] 1. PF > 1,2 e t-stat > 2
- [ ] 2. DSR >= 0,95 (N_TRIALS=38)
- [ ] 3. PF > 1 com custo x2
- [x] 4. >= 2 trimestres positivos com >= 20 trades

## Todas as variantes
```
               trades  pnl_usd_por_eth    pf  t_stat
tf    periodo                                       
1h    dev         136          -738.58  0.73   -1.30
      holdout     141           288.77  1.07    0.30
15min dev         399         -1754.29  0.72   -2.27
      holdout     358          -489.70  0.94   -0.40
4h    dev          42          -643.21  0.52   -1.38
      holdout      49          -935.27  0.60   -1.29
```

Primaria (1h) hold-out: DSR 0.030; PF com custo x2 = 0.93.

## Trimestres do hold-out (1h): periodo, trades, pnl USD por ETH
```
2024Q3   24      274.8
2024Q4   25     -328.1
2025Q1   27     -262.0
2025Q2   29      -49.8
2025Q3   27     1147.8
2025Q4    9     -493.9
```
