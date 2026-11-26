"""Baixa a base gratuita do DefiLlama (sem chave) para dados/raw/defillama e gera tabelas diarias.

Uso:
    python scripts/baixar_defillama.py --amostra 15   # mede o volume antes de baixar tudo
    python scripts/baixar_defillama.py                # baixa o que falta (retoma de onde parou)
    python scripts/baixar_defillama.py --tabelas      # so refaz as tabelas a partir do que ja esta em disco

Cada resposta fica inteira em JSON comprimido. Arquivo existente nao e baixado de novo.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

RAIZ = Path(__file__).resolve().parents[1] / "dados" / "raw" / "defillama"
API = "https://api.llama.fi"
STABLE = "https://stablecoins.llama.fi"
RESUMOS = {  # pasta: (dimensao, dataType)
    "taxas": ("fees", "dailyFees"),
    "receita": ("fees", "dailyRevenue"),
    "volume_dex": ("dexs", None),
    "volume_opcoes": ("options", "dailyNotionalVolume"),
}


class Cliente:
    """GET com intervalo minimo entre chamadas (vale para todas as threads) e recuo em 429/5xx."""

    def __init__(self, intervalo: float):
        self.intervalo = intervalo
        self.trava = threading.Lock()
        self.proximo = 0.0
        self.local = threading.local()
        self.bytes = 0
        self.limitado = 0

    def _vez(self) -> None:
        with self.trava:
            espera = self.proximo - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            self.proximo = time.monotonic() + self.intervalo

    def _pausar(self, segundos: float) -> None:
        with self.trava:
            self.proximo = max(self.proximo, time.monotonic() + segundos)

    def get(self, url: str) -> bytes:
        if not hasattr(self.local, "sessao"):
            self.local.sessao = requests.Session()
            self.local.sessao.headers["User-Agent"] = "coletor-dados/1.0"
        erro = ""
        for tentativa in range(6):
            self._vez()
            try:
                r = self.local.sessao.get(url, timeout=120)
            except requests.RequestException as e:
                erro = type(e).__name__
                time.sleep(2**tentativa)
                continue
            if r.status_code == 200:
                r.json()  # resposta truncada ou HTML nao vira arquivo
                with self.trava:
                    self.bytes += len(r.content)
                return r.content
            erro = f"HTTP {r.status_code}"
            if r.status_code == 429:
                self.limitado += 1
                pedido = r.headers.get("Retry-After", "")
                self._pausar(float(pedido) if pedido.isdigit() else 15 * (tentativa + 1))
            elif r.status_code >= 500:
                time.sleep(2**tentativa + random.random())
            else:
                break
        raise RuntimeError(erro)


def nome_seguro(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", texto)


def caminho(pasta: str, nome: str) -> Path:
    return RAIZ / pasta / f"{nome_seguro(nome)}.json.gz"


def salvar(destino: Path, conteudo: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".part")
    parcial.write_bytes(gzip.compress(conteudo, 6))
    parcial.replace(destino)


def ler(origem: Path):
    with gzip.open(origem, "rt", encoding="utf-8") as f:
        return json.load(f)


def catalogos(cli: Cliente) -> None:
    sem_graficos = "excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
    lista = {
        "protocols": f"{API}/protocols",
        "chains": f"{API}/v2/chains",
        "overview_fees": f"{API}/overview/fees?{sem_graficos}",
        "overview_dexs": f"{API}/overview/dexs?{sem_graficos}",
        "overview_options": f"{API}/overview/options?{sem_graficos}",
        "stablecoins": f"{STABLE}/stablecoins?includePrices=true",
        "stablecoinchains": f"{STABLE}/stablecoinchains",
    }
    for nome, url in lista.items():
        destino = caminho("catalogo", nome)
        if not destino.exists():
            salvar(destino, cli.get(url))
            print(f"catalogo {nome} ok", flush=True)


def tarefas() -> dict[str, list[tuple[str, str]]]:
    """Por grupo, a lista de (nome do arquivo, url)."""
    cat = {p.name.removesuffix(".json.gz"): ler(p) for p in (RAIZ / "catalogo").glob("*.json.gz")}
    grupos: dict[str, list[tuple[str, str]]] = {}

    chains = [c["name"] for c in cat["chains"] if c.get("name")]
    grupos["tvl_chain"] = [("_todas", f"{API}/v2/historicalChainTvl")] + [
        (c, f"{API}/v2/historicalChainTvl/{quote(c, safe='')}") for c in chains
    ]
    grupos["stable_chain"] = [("_todas", f"{STABLE}/stablecoincharts/all")] + [
        (c["name"], f"{STABLE}/stablecoincharts/{quote(c['name'], safe='')}")
        for c in cat["stablecoinchains"]
        if c.get("name")
    ]
    grupos["stable_ativo"] = [
        (f"{a['id']}_{a.get('symbol', '')}", f"{STABLE}/stablecoin/{a['id']}")
        for a in cat["stablecoins"]["peggedAssets"]
    ]
    for pasta, (dim, tipo) in RESUMOS.items():
        slugs = sorted({p.get("slug") or p.get("module") for p in cat[f"overview_{dim}"]["protocols"]} - {None})
        sufixo = f"?dataType={tipo}" if tipo else ""
        grupos[pasta] = [(s, f"{API}/summary/{dim}/{quote(s, safe='')}{sufixo}") for s in slugs]
    # Maiores primeiro: se a coleta for interrompida, o que importa ja esta em disco.
    protos = sorted((p for p in cat["protocols"] if p.get("slug")), key=lambda p: -(p.get("tvl") or 0))
    grupos["tvl_protocolo"] = [(p["slug"], f"{API}/protocol/{quote(p['slug'], safe='')}") for p in protos]
    return grupos


def sem_colisao(itens: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """No Windows, nomes que so diferem em maiusculas caem no mesmo arquivo: o segundo ganha um numero."""
    vistos: dict[str, int] = {}
    saida = []
    for nome, url in itens:
        chave = nome_seguro(nome).lower()
        vistos[chave] = vistos.get(chave, 0) + 1
        saida.append((nome if vistos[chave] == 1 else f"{nome}_{vistos[chave]}", url))
    return saida


def baixar(cli: Cliente,grupos: dict[str, list[tuple[str, str]]], threads: int) -> None:
    falhas = RAIZ / "falhas.tsv"
    for pasta, itens in grupos.items():
        faltam = [(n, u) for n, u in itens if not caminho(pasta, n).exists()]
        print(f"{pasta}: {len(itens)} itens, {len(faltam)} a baixar", flush=True)
        antes, inicio, erros = cli.bytes, time.monotonic(), 0

        def um(item, pasta=pasta):
            nome, url = item
            salvar(caminho(pasta, nome), cli.get(url))

        with ThreadPoolExecutor(threads) as pool:
            futuros = {pool.submit(um, i): i for i in faltam}
            for feito, fut in enumerate(as_completed(futuros), 1):
                try:
                    fut.result()
                except Exception as e:  # uma falha nao derruba a coleta; fica registrada
                    erros += 1
                    with falhas.open("a", encoding="utf-8") as f:
                        f.write(f"{pasta}\t{futuros[fut][0]}\t{e}\n")
                if feito % 200 == 0:
                    print(f"  {pasta} {feito}/{len(faltam)}  {(cli.bytes - antes) / 1e6:.0f} MB", flush=True)
        if faltam:
            disco = sum(p.stat().st_size for p in (RAIZ / pasta).glob("*.json.gz"))
            print(
                f"  fim {pasta}: {(cli.bytes - antes) / 1e6:.1f} MB lidos, {disco / 1e6:.1f} MB em disco, "
                f"{erros} falhas, {cli.limitado} respostas 429 ate agora, {time.monotonic() - inicio:.0f}s",
                flush=True,
            )


def dia(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def linhas(pasta: str, dados):
    """(data, valor em USD) de uma resposta, conforme o grupo."""
    if pasta == "tvl_chain":
        return [(dia(r["date"]), r.get("tvl")) for r in dados]
    if pasta == "tvl_protocolo":
        return [(dia(r["date"]), r.get("totalLiquidityUSD")) for r in dados.get("tvl") or []]
    if pasta == "stable_chain":
        return [(dia(r["date"]), sum((r.get("totalCirculatingUSD") or {}).values())) for r in dados]
    return [(dia(t), v) for t, v in dados.get("totalDataChart") or []]


def tabelas() -> None:
    destino = RAIZ / "tabelas"
    destino.mkdir(parents=True, exist_ok=True)
    for pasta in ("tvl_chain", "tvl_protocolo", "stable_chain", *RESUMOS):
        arquivos = sorted((RAIZ / pasta).glob("*.json.gz"))
        total, ruins = 0, 0
        with gzip.open(destino / f"{pasta}.csv.gz", "wt", encoding="utf-8", newline="") as f:
            saida = csv.writer(f)
            saida.writerow(["data", "nome", "usd"])
            for arq in arquivos:
                nome = arq.name.removesuffix(".json.gz")
                try:
                    novas = linhas(pasta, ler(arq))
                except (KeyError, TypeError, ValueError, AttributeError):
                    ruins += 1
                    continue
                saida.writerows((d, nome, v) for d, v in novas)
                total += len(novas)
        print(f"tabela {pasta}: {len(arquivos)} arquivos, {total} linhas, {ruins} ilegiveis", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amostra", type=int, default=0, help="baixa so N itens por grupo e projeta o total")
    ap.add_argument("--intervalo", type=float, default=0.25, help="segundos minimos entre requisicoes")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--tabelas", action="store_true", help="so refaz as tabelas")
    ap.add_argument("--pular", nargs="*", default=[], help="grupos que ficam de fora (ex.: tvl_protocolo)")
    args = ap.parse_args()

    if not args.tabelas:
        (RAIZ / "falhas.tsv").unlink(missing_ok=True)
        cli = Cliente(args.intervalo)
        catalogos(cli)
        grupos = {g: sem_colisao(i) for g, i in tarefas().items() if g not in args.pular}
        if args.amostra:
            # Espalha a amostra pela lista: pegar so o comeco (os maiores) superestima o total.
            for pasta, itens in grupos.items():
                passo = max(1, len(itens) // args.amostra)
                escolhidos = itens[::passo][: args.amostra]
                antes = cli.bytes
                baixar(cli, {pasta: escolhidos}, args.threads)
                presentes = [caminho(pasta, n) for n, _ in escolhidos if caminho(pasta, n).exists()]
                if presentes:
                    media = sum(p.stat().st_size for p in presentes) / len(presentes)
                    lido = (cli.bytes - antes) / len(presentes)
                    print(
                        f"  PROJECAO {pasta}: {len(itens)} itens, ~{media * len(itens) / 1e6:.0f} MB em disco, "
                        f"~{lido * len(itens) / 1e6:.0f} MB descomprimidos",
                        flush=True,
                    )
            return
        baixar(cli, grupos, args.threads)
    tabelas()


if __name__ == "__main__":
    main()
