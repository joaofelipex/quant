# eth_ml - ordens limitadas (ETHUSDT)

Sinal logit m=1,0% d=0,10; custo mercado 5+2 bps por lado; N_TRIALS=24 (DSR por trade). `execucao` = fracao de sinais em que a ordem limitada foi preenchida.

```
                                 sinais  execucao  trades  bps_por_trade  win_rate  t_stat  dsr_trade  sharpe_barra
variante                                                                                                           
referencia_mercado                  322     1.000     322          3.339     0.562   0.240      0.042         0.133
limite_maker2_thr0_saida_market     323     0.997     322          8.266     0.581   0.595      0.086         0.328
limite_maker2_thr0_saida_limit      323     0.997     322         12.092     0.602   0.870      0.139         0.480
limite_maker2_thr2_saida_market     326     0.972     317          2.192     0.568   0.157      0.035         0.087
limite_maker2_thr2_saida_limit      326     0.972     317          4.030     0.577   0.287      0.046         0.159
limite_maker5_thr0_saida_market     323     0.997     322          5.266     0.578   0.379      0.056         0.209
limite_maker5_thr0_saida_limit      323     0.997     322          6.129     0.575   0.441      0.064         0.244
limite_maker5_thr2_saida_market     326     0.972     317         -0.808     0.565  -0.058      0.021        -0.032
limite_maker5_thr2_saida_limit      326     0.972     317         -1.857     0.549  -0.132      0.017        -0.073
```
