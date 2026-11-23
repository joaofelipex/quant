# funding_carry - resultados

Periodo: 2020-01-01 a 2025-10-31. Hold-out a partir de 2023-07-01.
Primaria: BTC+ETH, L=14 dias, piso 5% a.a.
Custo 20 bps/troca, margem 20%.
Retornos SOBRE O CAPITAL (nocional x (1 + margem)); caixa e margem rendem zero.

## Veredito: **REPROVADA**
- [x] 1. Retorno liquido anual no hold-out > 4%
- [x] 2. DSR >= 0,95 (N_TRIALS=20)
- [x] 3. Retorno anual > 0 com custos x3 (hold-out)
- [x] 4. Bootstrap em blocos: P(retorno medio <= 0) < 5% (hold-out)
- [ ] 5. Zero dias de liquidacao com a posicao ligada e drawdown do hold-out >= -5%

## Desempenho da variante primaria (liquido de custos)
```
                       ret_anual    vol  sharpe  max_dd  pior_30d  funding_ano  base_ano  custo_ano  tempo_ligado
dev                        0.125  0.016   7.648  -0.020    -0.011        0.145    -0.001     -0.019         0.715
holdout                    0.052  0.006   8.055  -0.007    -0.006        0.067    -0.000     -0.015         0.675
total                      0.095  0.013   7.129  -0.020    -0.011        0.114    -0.001     -0.017         0.699
sempre_ligado_dev          0.146  0.016   9.155  -0.012    -0.011          NaN       NaN        NaN           NaN
sempre_ligado_holdout      0.075  0.005  14.682  -0.001     0.000          NaN       NaN        NaN           NaN
sempre_ligado_total        0.117  0.013   9.121  -0.012    -0.011          NaN       NaN        NaN           NaN
```

DSR (hold-out, N_TRIALS=20): 1.000. Bootstrap em blocos da media diaria (hold-out): IC 90% de retorno
anual [3.1%, 7.3%], P(media <= 0) = 0.0%.

## Risco de cauda (BTC+ETH): a perna vendida do perpetuo pode ser liquidada
Criterio pre-registrado (alta do perpetuo, high/abertura, >= margem livre de 19.5%): **10 dias com a posicao
ligada**. Pela maxima do SPOT (proxy do preco de marcacao, que e o que a corretora usa para liquidar): **9
dias com a posicao ligada**, ou seja, altas reais de 20% ou mais em 24 h. A maxima do perpetuo tem tambem mechas
anomalas: a pior foi ETH 2020-03-13 (+202% no perpetuo contra +30% no spot).
Maior alta do spot com a posicao ligada: 30.6%.

```
                  alta_perp  alta_spot  ligado
ativo dia                                     
BTC   2020-03-13      0.254      0.241    True
      2021-02-08      0.214      0.206    True
      2021-07-26      0.362      0.146   False
      2023-10-23      0.200      0.158   False
ETH   2020-01-14      0.191      0.196   False
      2020-03-13      2.020      0.297    True
      2020-03-19      0.214      0.212    True
      2020-04-06      0.206      0.205    True
      2021-01-03      0.319      0.306    True
      2021-01-04      0.198      0.189    True
      2021-05-20      0.224      0.226    True
      2021-05-24      0.276      0.276    True
      2022-11-10      0.226      0.224   False
      2024-05-20      0.205      0.203    True
      2025-05-08      0.230      0.229   False
```

Margem maior evita a liquidacao mas dilui o retorno (mais capital parado):
```
            ret_anual_holdout  dias_liq_perp  dias_liq_proxy_spot
margem_20%             0.0517           10.0                  9.0
margem_35%             0.0460            1.0                  0.0
margem_50%             0.0414            1.0                  0.0
```
Nao modelado: margem unificada/portfolio margin (o spot como colateral reduziria o risco) e recomposicao intradiaria.

## Estresse de custos (primaria, retorno anual do hold-out)
```
          ret_anual_holdout
custo_x0             0.0667
custo_x1             0.0517
custo_x2             0.0367
custo_x3             0.0217
custo_x5            -0.0082
```

## Por ano (primaria; soma dos retornos diarios sobre o capital)
```
          ret_liquido  funding   base  custo  tempo_ligado  funding_bruto_btc_eth_aa
datetime                                                                            
2020            0.167    0.182 -0.005 -0.010         0.854                     0.223
2021            0.275    0.282 -0.000 -0.007         0.895                     0.341
2022           -0.017    0.016  0.000 -0.033         0.340                     0.025
2023            0.038    0.060 -0.000 -0.022         0.753                     0.081
2024            0.089    0.100  0.001 -0.012         0.833                     0.124
2025            0.005    0.023  0.000 -0.018         0.484                     0.050
```

## Por ativo (hold-out)
```
     ret_anual  sharpe  max_dd
BTC      0.044   5.430  -0.014
ETH      0.059   8.575  -0.007
```

## Grade de variantes (retorno anual liquido; robustez, nao selecao)
```
                        ret_dev  ret_holdout  ret_total  sharpe_holdout
universo variante                                                      
BTC+ETH  sempre_ligado    0.146        0.075      0.117          14.682
         L7_H0%           0.134        0.065      0.107          10.804
         L7_H5%           0.117        0.040      0.086           5.393
         L7_H10%          0.115        0.034      0.083           5.194
         L14_H0%          0.141        0.070      0.113          12.709
         L14_H5%          0.125        0.052      0.095           8.055
         L14_H10%         0.119        0.034      0.085           5.542
         L30_H0%          0.140        0.074      0.114          14.378
         L30_H5%          0.127        0.058      0.099           9.689
         L30_H10%         0.117        0.039      0.086           7.149
6 pares  sempre_ligado    0.091        0.057      0.077           9.382
         L7_H0%           0.122        0.049      0.093           7.867
         L7_H5%           0.114        0.034      0.082           5.274
         L7_H10%          0.108        0.033      0.078           5.736
         L14_H0%          0.126        0.058      0.098          10.030
         L14_H5%          0.121        0.046      0.091           7.856
         L14_H10%         0.115        0.035      0.083           6.375
         L30_H0%          0.122        0.062      0.098          11.240
         L30_H5%          0.114        0.051      0.089           9.412
         L30_H10%         0.108        0.037      0.080           7.054
```
