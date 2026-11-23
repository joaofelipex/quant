# tsmom_cripto - resultados

Periodo: 2020-01-01 a 2025-10-31.
Dev 2020-09-01 a 2023-07-01; hold-out depois.
Variante primaria: base / long_short. Custo 7 bps + funding real.

## Veredito: **REPROVADA**
- [ ] 1. Sharpe liquido > 0 e alfa t > 2 (hold-out)
- [ ] 2. DSR >= 0,95 (N_TRIALS=30)
- [x] 3. Sharpe > 0 com custos x2 (hold-out)
- [ ] 4. Bootstrap: P(Sharpe <= 0) < 5%
- [ ] 5. Positivo sem qualquer ativo (hold-out) e em todos os anos

## Desempenho da variante primaria (liquido de custos e funding)
```
               ret_anual    vol  sharpe  max_dd  calmar  funding_ano  custo_ano  giro_ano
dev                0.110  0.115   0.951  -0.139   0.792       -0.020     -0.006     7.881
holdout            0.091  0.113   0.804  -0.162   0.561       -0.013     -0.011    15.477
total              0.101  0.114   0.885  -0.162   0.624       -0.017     -0.008    11.314
cesta_dev          1.010  0.848   1.191  -0.809   1.249          NaN        NaN       NaN
btc_dev            0.564  0.680   0.830  -0.766   0.737          NaN        NaN       NaN
cesta_holdout      0.850  0.604   1.408  -0.429   1.982          NaN        NaN       NaN
btc_holdout        0.648  0.463   1.400  -0.281   2.308          NaN        NaN       NaN
cesta_total        0.938  0.748   1.255  -0.809   1.160          NaN        NaN       NaN
btc_total          0.602  0.592   1.018  -0.766   0.786          NaN        NaN       NaN
```

Hold-out vs cesta equiponderada: beta 0.04 (t 1.6), **alfa 5.3% a.a. (t 0.75)**.
Periodo total: beta 0.03, alfa 7.3% a.a. (t 1.43).
DSR (hold-out, N_TRIALS=30): 0.200.
Bootstrap em blocos do Sharpe (hold-out): IC 90% [-0.38, 1.97], P(Sharpe <= 0) = 13.6%.

## Todas as variantes (robustez; Sharpe liquido)
```
                   sharpe_dev  sharpe_holdout  sharpe_total  giro_ano
variante                                                             
rapido_long_short       1.142           0.790         0.983    16.011
rapido_long_only        1.485           1.818         1.638     6.798
base_long_short         0.951           0.804         0.885    10.778
base_long_only          1.379           1.704         1.530     4.929
lento_long_short        1.300           1.153         1.236     5.830
lento_long_only         1.626           1.356         1.495     2.656
```

## Estresse de custos (variante primaria)
```
          sharpe_holdout  sharpe_total
custo_x0           0.900         0.955
custo_x1           0.804         0.885
custo_x2           0.708         0.816
custo_x4           0.516         0.678
```

## Sem cada ativo (variante primaria)
```
         sharpe_holdout  sharpe_total
sem_BTC           0.915         0.983
sem_ETH           0.967         1.022
sem_BNB           0.758         0.836
sem_SOL           0.811         0.911
sem_XRP           0.835         1.046
sem_ADA           0.994         1.034
```

## Por ano (variante primaria vs cesta; retorno somado dos dias)
```
          estrategia_ret  estrategia_sharpe  cesta_ret
datetime                                              
2020               0.217              1.989      1.666
2021               0.185              1.758      2.988
2022               0.076              0.606     -1.015
2023               0.066              0.653      1.199
2024               0.108              0.869      0.959
2025              -0.005             -0.056      0.300
```

## Pesos alvo no ultimo dia (2025-10-31)
```
          peso
BTCUSDT  0.030
ETHUSDT  0.017
BNBUSDT  0.012
SOLUSDT  0.014
XRPUSDT  0.016
ADAUSDT -0.027
```
