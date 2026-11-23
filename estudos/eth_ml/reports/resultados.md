# eth_ml - resultados OOS

OOS: 2022-06-25 a 2025-10-06 (28798 barras). AUC OOS: logit 0.5444, gbm 0.5514 (0,5 = sem informacao).
Custo: 5 bps taxa + 2 bps slippage por lado. DSR com N_TRIALS=7 (por barra; as barras tem retornos sobrepostos pelo horizonte, entao e otimista).

```
               ret_anual  sharpe  max_dd  giro_ano  tempo_posicionado  sharpe_bruto  sharpe_x2  sharpe_x3  dsr
variante                                                                                                      
buy_and_hold       0.619   0.968  -0.653     0.000              1.000         0.968      0.967      0.967  NaN
momentum_r24      -1.693  -2.641  -0.998  1759.422              1.000        -0.721     -4.537     -6.389  0.0
logit_thr0.00     -2.172  -3.380  -1.000  3978.168              1.000         0.958     -7.624    -11.692  0.0
logit_thr0.02     -1.448  -2.667  -0.995  3465.307              0.598         1.805     -7.081    -11.381  0.0
logit_thr0.05     -0.700  -1.751  -0.926  1774.023              0.240         1.358     -4.823     -7.817  0.0
gbm_thr0.00       -1.720  -2.677  -0.999  4205.700              1.000         1.914     -7.177    -11.493  0.0
gbm_thr0.02       -1.786  -3.204  -0.999  3972.388              0.741         1.790     -8.118    -12.878  0.0
gbm_thr0.05       -1.388  -3.244  -0.993  2844.460              0.407         1.412     -7.827    -12.265  0.0
```

Melhor por Sharpe liquido: **logit_thr0.05**. Sharpe por ano:

```
datetime
2022   -1.25
2023   -2.14
2024   -2.77
2025   -0.91
```
