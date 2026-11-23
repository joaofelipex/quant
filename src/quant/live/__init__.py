"""Operacao ao vivo (esqueleto): feed de barras -> estrategia -> risco -> executor.

A estrategia e a MESMA do backtest (``quant.strategies``); o que muda e so o destino das ordens.
Comece sempre em modo ``paper``. Nada aqui libera uma estrategia para conta real: a regra do README continua valendo.
"""
