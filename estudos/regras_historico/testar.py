"""Regras de entrada (so comprado) em 19 criptos, velas de 1 h: cada uma contra a entrada em hora qualquer.

    python estudos/regras_historico/testar.py [--custo 30]

Sinal calculado no fechamento de uma barra, entrada na abertura da seguinte, saida no fechamento H barras depois, sem
posicoes sobrepostas na mesma moeda. A referencia ("hora qualquer") e o retorno medio de TODAS as barras daquela moeda
no mesmo periodo e prazo: so o que passa disso e merito da regra, o resto e o mercado ter subido ou caido.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
PRECOS = RAIZ / "dados" / "raw" / "binance" / "h1_19"
TAXAS = RAIZ / "dados" / "raw" / "defillama" / "tabelas" / "taxas.csv.gz"
MOEDAS = "BTC ETH SOL XRP BNB DOGE ADA LINK LTC BCH DOT NEAR UNI AAVE SUI XLM HBAR WLD ZEC".split()
# nome do arquivo de taxas no DefiLlama (so moedas com rede/protocolo proprio e inequivoco)
LLAMA = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "bsc", "DOGE": "doge", "ADA": "cardano",
         "LTC": "litecoin", "DOT": "polkadot", "NEAR": "near", "UNI": "uniswap", "AAVE": "aave", "SUI": "sui",
         "XLM": "stellar", "HBAR": "hedera", "LINK": "chainlink", "BCH": "bitcoin-cash", "ZEC": "zcash"}
PRAZOS = (4, 24, 72, 168)


def taxas_em_alta() -> dict[str, pd.Series]:
    """Por moeda, serie diaria True quando as taxas dos ultimos 30 dias superam as dos 30 anteriores.
    So fica disponivel 2 dias depois (o dado do dia fecha e e publicado depois)."""
    if not TAXAS.exists():
        return {}
    t = pd.read_csv(TAXAS)
    t["nome"] = t["nome"].str.lower()
    out = {}
    for moeda, nome in LLAMA.items():
        s = t[t.nome == nome]
        if s.empty:
            continue
        s = s.set_index(pd.to_datetime(s["data"]))["usd"].astype(float).sort_index().asfreq("D")
        m = s.rolling(30, min_periods=25).sum()
        alta = (m > m.shift(30)).where(m.notna() & m.shift(30).notna())
        out[moeda] = alta.shift(2, freq="D")
    return out


def sinais(d: pd.DataFrame, alta: pd.Series | None) -> dict[str, pd.Series]:
    c = d["close"]
    r1, r4, r24 = c.pct_change(), c.pct_change(4), c.pct_change(24)
    r7d, r30d = c.pct_change(168), c.pct_change(720)
    vol = r1.rolling(168).std()
    s = {
        "momento_curto (como a IA)": (r1 > vol) & (r4 > 0) & (r24 > 0),
        "queda_forte_4h": r4 < -2 * vol * 2,
        "queda_4h_em_alta_30d": (r4 < -1.5 * vol * 2) & (r30d > 0),
        "rompimento_55h": c > d["high"].rolling(55).max().shift(1),
        "tendencia_7d_30d": (r7d > 0) & (r30d > 0),
    }
    if alta is not None:
        a = alta.reindex(d["datetime"].dt.floor("D")).to_numpy()
        filtro = pd.Series(a == True, index=d.index)  # noqa: E712 - NaN (sem dado) nao passa
        s["taxas_em_alta"] = filtro
        s["tendencia_7d_30d + taxas"] = s["tendencia_7d_30d"] & filtro
        s["queda_forte_4h + taxas"] = s["queda_forte_4h"] & filtro
    return s


def operar(sinal: np.ndarray, futuro: np.ndarray, prazo: int) -> list[int]:
    """Indices das barras de sinal usadas, sem sobrepor posicoes."""
    usados, livre = [], 0
    for i in np.flatnonzero(sinal):
        if i >= livre and np.isfinite(futuro[i]):
            usados.append(i)
            livre = i + prazo
    return usados


def rodar(custo: float) -> pd.DataFrame:
    alta = taxas_em_alta()
    dados = {m: pd.read_csv(PRECOS / f"{m}USDT_1h.csv", parse_dates=["datetime"]) for m in MOEDAS}
    inicio = max(d.datetime.min() for d in dados.values()) + pd.Timedelta("720h")
    fim = min(d.datetime.max() for d in dados.values())
    meio = inicio + (fim - inicio) / 2
    trades, base = [], {}
    for m, d in dados.items():
        s = sinais(d, alta.get(m))
        for prazo in PRAZOS:
            # entra na abertura da barra i+1, sai no fechamento da barra i+prazo (em bps)
            fut = ((d["close"].shift(-prazo) / d["open"].shift(-1) - 1) * 1e4).to_numpy()
            saida = d["datetime"].shift(-prazo)
            periodos = {"treino": (d.datetime >= inicio) & (saida < meio),
                        "teste": (d.datetime >= meio) & (saida <= fim)}
            for nome_p, mask in periodos.items():
                base[(m, prazo, nome_p)] = np.nanmean(fut[mask.to_numpy()])
                for regra, sig in s.items():
                    for i in operar((sig & mask).to_numpy(), fut, prazo):
                        trades.append((regra, prazo, nome_p, m, d.datetime.iloc[i], fut[i],
                                       fut[i] - base[(m, prazo, nome_p)]))
    print(f"periodo {inicio.date()} -> {fim.date()}, corte {meio.date()}, custo {custo:g} bps ida e volta")
    return pd.DataFrame(trades, columns=["regra", "prazo", "periodo", "moeda", "t", "bruto", "excesso"])


def resumo(tr: pd.DataFrame, custo: float) -> pd.DataFrame:
    linhas = []
    for (regra, prazo, periodo), g in tr.groupby(["regra", "prazo", "periodo"]):
        # moedas andam juntas e trades vizinhos se sobrepoem: a unidade do teste e a semana, nao o trade
        semana = g.groupby(g["t"].dt.to_period("W"))["excesso"].mean()
        t = semana.mean() / semana.std() * np.sqrt(len(semana)) if len(semana) > 2 and semana.std() > 0 else 0.0
        linhas.append(dict(regra=regra, prazo=prazo, periodo=periodo, n=len(g), liquido=g.bruto.mean() - custo,
                           excesso=g.excesso.mean(), t=t))
    return pd.DataFrame(linhas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--custo", type=float, default=30.0, help="bps ida e volta (cripto na demo: ~24 de taxa + spread)")
    args = ap.parse_args()
    r = resumo(rodar(args.custo), args.custo)
    w = r.pivot_table(index=["regra", "prazo"], columns="periodo", values=["n", "liquido", "excesso", "t"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.sort_values("t_treino", ascending=False)
    ordem = [f"{a}_{p}" for p in ("treino", "teste") for a in ("n", "liquido", "excesso", "t")]
    print(w[ordem].astype(float).round(1).to_string())
    # com dezenas de combinacoes, t de 2 aparece por sorte; exige-se ~3 no teste, alem de ganhar nos dois periodos
    ok = w[(w.liquido_treino > 0) & (w.liquido_teste > 0) & (w.excesso_treino > 0) & (w.excesso_teste > 0)]
    print(f"\ncombinacoes testadas: {len(w)}; liquidas e acima da hora qualquer nos dois periodos: {len(ok)}; "
          f"dessas, com t_teste >= 3: {int((ok.t_teste >= 3).sum())}")
    if len(ok):
        print(ok[["liquido_treino", "excesso_treino", "t_treino", "liquido_teste", "excesso_teste", "t_teste"]]
              .astype(float).round(1).to_string())


if __name__ == "__main__":
    main()
