"""Baixa series do SGS do Banco Central (api.bcb.gov.br) para CSV.

Uso:
    python -m quant.data.fetch_bcb            # baixa todas as series do catalogo abaixo
    python -m quant.data.fetch_bcb selic_meta # so uma
Saida: dados/raw/bcb/<nome>.csv (data, valor)

A API limita series diarias a janelas menores que 10 anos por consulta, por isso baixamos em blocos.
"""
import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[3] / "dados" / "raw" / "bcb"

# nome -> (codigo SGS, descricao, inicio)
CATALOGO = {
    "selic_meta": (432, "Meta Selic (% a.a.)", 2000),
    "selic_diaria": (11, "Selic efetiva diaria (% a.d.)", 1995),
    "cdi_diario": (12, "CDI diario (% a.d.)", 1995),
    "ipca_mensal": (433, "IPCA variacao mensal (%)", 1995),
    "usdbrl_venda": (1, "Dolar comercial venda (R$)", 1995),
    "igpm_mensal": (189, "IGP-M variacao mensal (%)", 1995),
    "desemprego_pnad": (24369, "Taxa de desocupacao PNAD (%)", 2012),
}


def get_json(url: str, rotulo: str, tentativas: int = 5):
    """O SGS as vezes devolve uma pagina HTML de erro; repete com espera crescente."""
    for i in range(tentativas):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=60).read())
        except Exception as e:
            if i == tentativas - 1:
                sys.exit(f"Falha ao baixar {rotulo}: {e}")
            time.sleep(2 * (i + 1))


def fetch_series(code: int, start_year: int) -> pd.DataFrame:
    frames = []
    year = start_year
    this_year = date.today().year
    while year <= this_year:
        end_year = min(year + 8, this_year)
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
            f"?formato=json&dataInicial=01/01/{year}&dataFinal=31/12/{end_year}"
        )
        data = get_json(url, f"serie {code} ({year}-{end_year})")
        if data:
            frames.append(pd.DataFrame(data))
        year = end_year + 1
    if not frames:
        return pd.DataFrame(columns=["data", "valor"])
    df = pd.concat(frames)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.drop_duplicates("data").sort_values("data")
    # algumas series (ex.: meta Selic) trazem datas futuras repetidas
    return df[df["data"] <= pd.Timestamp(date.today())].reset_index(drop=True)


def main():
    nomes = sys.argv[1:] or list(CATALOGO)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for nome in nomes:
        if nome not in CATALOGO:
            sys.exit(f"Serie desconhecida: {nome}. Opcoes: {', '.join(CATALOGO)}")
        code, desc, start = CATALOGO[nome]
        df = fetch_series(code, start)
        path = OUT_DIR / f"{nome}.csv"
        df.to_csv(path, index=False)
        print(f"{nome} (SGS {code}) - {desc}: {len(df)} linhas, {df['data'].min().date()} a {df['data'].max().date()}")


if __name__ == "__main__":
    main()
