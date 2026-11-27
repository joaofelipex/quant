"""Entrar com ordem limite compensa? Horas e lados sorteados, velas de 1 min da demo, saida a mercado em 1 h ou 4 h.

A ordem no bid (compra) ou no ask (venda) so conta como executada se, em ate 5 min, o outro lado do livro CHEGA ao
preco dela (criterio conservador). Compara com entrar a mercado no mesmo instante, e a mercado so nos instantes em
que a limite teria executado: a diferenca entre os dois e a selecao adversa.
"""
import numpy as np
import pandas as pd
from comum import MAKER, TAKER, velas

bid, ask, _, _, cls, _ = velas()
rng = np.random.default_rng(7)
linhas = []
for a in bid:
    b, k = bid[a].to_numpy(), ask[a].to_numpy()
    validos = np.flatnonzero(~np.isnan(b[:-300]))
    if len(validos) < 500:
        continue
    for i in rng.choice(validos, 600):
        lado = 1 if rng.random() < 0.5 else -1
        entra, sai = (k, b) if lado > 0 else (b, k)  # a mercado compra no ask e vende no bid
        limite = b[i] if lado > 0 else k[i]
        outro = entra[i + 1:i + 6]
        toca = np.flatnonzero(outro <= limite) if lado > 0 else np.flatnonzero(outro >= limite)
        for h in (60, 240):
            mercado = lado * (sai[i + 1 + h] / entra[i + 1] - 1) * 1e4 - 2 * TAKER[cls[a]]
            r = {"cls": cls[a], "h": h, "mercado": mercado, "executou": len(toca) > 0}
            if len(toca):
                j = i + 1 + toca[0]
                r["limite"] = lado * (sai[j + h] / limite - 1) * 1e4 - MAKER[cls[a]] - TAKER[cls[a]]
            linhas.append(r)
t = pd.DataFrame(linhas)
t = t[(t.mercado.abs() < 1500) & ~(t.limite.abs() >= 1500)]
g = t.groupby(["cls", "h"]).agg(ordens=("mercado", "size"), executou=("executou", "mean"),
                                a_mercado=("mercado", "mean"), limite_entrada=("limite", "mean"))
g["mercado_quando_executa"] = t[t.executou].groupby(["cls", "h"]).mercado.mean()
g["mercado_quando_nao"] = t[~t.executou].groupby(["cls", "h"]).mercado.mean()
g["executou"] *= 100
print(g.round(1).to_string())
