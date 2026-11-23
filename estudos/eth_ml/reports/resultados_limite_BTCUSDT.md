# eth_ml - ordens limitadas (BTCUSDT)

Sinal logit m=1,0% d=0,10; custo mercado 5+2 bps por lado; N_TRIALS=24 (DSR por trade). `execucao` = fracao de sinais em que a ordem limitada foi preenchida.

```
                                 sinais  execucao  trades  bps_por_trade  win_rate  t_stat  dsr_trade  sharpe_barra
variante                                                                                                           
referencia_mercado                  210     1.000     210         -0.053     0.505  -0.004      0.024        -0.002
limite_maker2_thr0_saida_market     211     0.972     205          3.931     0.512   0.314      0.048         0.173
limite_maker2_thr0_saida_limit      211     0.972     205          6.719     0.512   0.533      0.074         0.295
limite_maker2_thr2_saida_market     211     0.953     201          0.209     0.493   0.016      0.025         0.009
limite_maker2_thr2_saida_limit      211     0.953     201          0.822     0.488   0.064      0.028         0.036
limite_maker5_thr0_saida_market     211     0.972     205          0.931     0.507   0.074      0.028         0.041
limite_maker5_thr0_saida_limit      211     0.972     205          0.778     0.502   0.062      0.028         0.034
limite_maker5_thr2_saida_market     211     0.953     201         -2.791     0.488  -0.219      0.014        -0.121
limite_maker5_thr2_saida_limit      211     0.953     201         -5.044     0.478  -0.394      0.009        -0.218
```
