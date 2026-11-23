# eth_ml - ordens limitadas (SOLUSDT)

Sinal logit m=1,0% d=0,10; custo mercado 5+2 bps por lado; N_TRIALS=24 (DSR por trade). `execucao` = fracao de sinais em que a ordem limitada foi preenchida.

```
                                 sinais  execucao  trades  bps_por_trade  win_rate  t_stat  dsr_trade  sharpe_barra
variante                                                                                                           
referencia_mercado                  554     1.000     554         -1.772     0.498  -0.126      0.018        -0.069
limite_maker2_thr0_saida_market     556     0.995     553          2.477     0.506   0.174      0.036         0.096
limite_maker2_thr0_saida_limit      556     0.995     553          2.955     0.517   0.211      0.039         0.117
limite_maker2_thr2_saida_market     557     0.980     546          1.325     0.504   0.093      0.030         0.051
limite_maker2_thr2_saida_limit      557     0.980     546          0.056     0.513   0.004      0.024         0.002
limite_maker5_thr0_saida_market     556     0.995     553         -0.523     0.501  -0.037      0.022        -0.020
limite_maker5_thr0_saida_limit      556     0.995     553         -2.980     0.503  -0.213      0.014        -0.118
limite_maker5_thr2_saida_market     557     0.980     546         -1.675     0.498  -0.117      0.018        -0.065
limite_maker5_thr2_saida_limit      557     0.980     546         -5.840     0.498  -0.413      0.008        -0.228
```
