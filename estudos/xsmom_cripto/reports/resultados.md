# xsmom_cripto - resultados

## Veredito: **REPROVADA**
- [ ] 1. Sharpe liquido > 0 e alfa t > 2
- [ ] 2. DSR >= 0,95 (N_TRIALS=33)
- [x] 3. Sharpe > 0 com custos x2
- [ ] 4. Bootstrap: P(Sharpe <= 0) < 5%
- [x] 5. Positivo sem cada ativo e em todos os anos (2023+)

## Desempenho da variante primaria (lb60, liquido)
```
         ret_anual    vol  sharpe  max_dd  calmar
dev         -0.126  0.388  -0.325  -0.594  -0.212
holdout      0.287  0.276   1.040  -0.232   1.240
total        0.061  0.342   0.178  -0.615   0.099
```

Hold-out vs cesta: beta 0.06, alfa 23.8% a.a. (t 1.41). DSR 0.294.
Bootstrap em blocos (hold-out): IC 90% [-0.04, 2.03], P(Sharpe <= 0) = 5.6%.
Sharpe hold-out com custos x2: 0.97.

## Robustez (janelas)
```
      sharpe_dev  sharpe_holdout
lb60      -0.325           1.040
lb30       0.594           0.146
lb90       0.141           0.562
```

## Sem cada ativo (Sharpe hold-out)
```
             sharpe_holdout
sem_BTCUSDT           0.788
sem_ETHUSDT           0.807
sem_BNBUSDT           1.250
sem_SOLUSDT           0.669
sem_XRPUSDT           0.355
sem_ADAUSDT           0.338
```

## Retorno somado por ano
```
          estrategia_ret
datetime                
2020               0.298
2021              -0.079
2022              -0.239
2023               0.118
2024               0.162
2025               0.164
```
