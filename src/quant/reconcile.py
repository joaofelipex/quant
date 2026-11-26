"""Reescreve o historico local de trades com o resultado que a CORRETORA registrou.

    python -m quant.reconcile            # so mostra o que mudaria
    python -m quant.reconcile --aplicar  # grava, depois de copiar o original para trades.csv.antes-<data>

Cada posicao encerrada na corretora vira exatamente uma linha, com o resultado dela (ja com as duas taxas). A linha
local mais proxima no tempo empresta o motivo (e com ele a marca "ia"), os precos e o horario. Linhas locais repetidas
somem; linha sem execucao correspondente fica, com resultado zero e uma marca. Rodar com robo e IA parados.
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import observ
from .manual import TRADE_FIELDS

MATCH_S = 900  # o stop da corretora so e notado no passo seguinte do robo
SEM_PAR = " [sem execucao na corretora]"


def _epoch(ts: str) -> float:
    d = datetime.fromisoformat(str(ts)[:19])
    return d.replace(tzinfo=timezone.utc).timestamp()


def _asset(row: dict) -> str | None:
    origem = row.get("origem", "")
    return origem.split(":", 1)[1] if ":" in origem else None


def rebuild(rows: list[dict], trips: list[dict]) -> list[dict]:
    """Linhas novas do historico. Linhas de outras corretoras (paper) passam intactas."""
    nossas = [i for i, r in enumerate(rows) if r.get("origem", "").startswith("kalshi")]
    fechadas = sorted((v for v in trips if v["fim"] is not None), key=lambda v: v["fim"])
    par: dict[int, dict] = {}   # linha -> posicao
    usadas: set[int] = set()    # posicoes ja com linha
    candidatos = sorted((abs(_epoch(rows[i]["ts"]) - v["fim"]), i, k) for i in nossas for k, v in enumerate(fechadas)
                        if _asset(rows[i]) in (None, v["asset"]))
    for dist, i, k in candidatos:
        if dist <= MATCH_S and i not in par and k not in usadas:
            par[i] = fechadas[k]
            usadas.add(k)
    repetidas = {i for dist, i, k in candidatos if dist <= MATCH_S and i not in par and _asset(rows[i])}

    out = []
    for i, r in enumerate(rows):
        if i not in nossas:
            out.append(r)
        elif i in par:
            v = par[i]
            out.append({**r, "pnl": f"{v['bruto'] - v['taxa']:.4f}"})
        elif i not in repetidas:
            motivo = r.get("motivo", "")
            out.append({**r, "pnl": "0.0000", "motivo": motivo if motivo.endswith(SEM_PAR) else motivo + SEM_PAR})
    for k, v in enumerate(fechadas):
        if k not in usadas:
            quando = datetime.fromtimestamp(v["fim"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            motivo = ("ia: " if v["quem"] == "ia" else "") + "conciliado com a corretora"
            out.append({"ts": quando, "origem": f"kalshi/testnet:{v['asset']}", "side": v.get("lado", 1), "qty": "0",
                        "entrada": "0", "saida": "0", "pnl": f"{v['bruto'] - v['taxa']:.4f}", "motivo": motivo})
    return sorted(out, key=lambda r: str(r["ts"]))


def total(rows: list[dict]) -> float:
    return sum(float(r["pnl"]) for r in rows if r.get("origem", "").startswith("kalshi"))


def main(argv: list[str] | None = None, env=os.environ.get) -> int:
    from . import agent
    from .live import assets as assets_mod
    from .live.config import build_kalshi

    args = sys.argv[1:] if argv is None else argv
    if env("QUANT_MODE") != "testnet" or env("QUANT_VENUE") != "kalshi":
        raise SystemExit("conciliacao: so com a Kalshi demo")
    path = Path(env("QUANT_TRADES_LOG", "/var/lib/quant/trades.csv"))
    ex = build_kalshi("testnet", env, assets_mod.ticker("BTC"))
    fills = observ.pages(ex, "/margin/fills", "fills", limit=1000)
    decisions = observ._jsonl(Path(env("QUANT_AGENT_DIR", str(agent.AGENT_DIR))) / "decisions.jsonl")
    trips = observ.round_trips(fills, observ.ai_opens(decisions))
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    novas = rebuild(rows, trips)
    alvo = sum(v["bruto"] - v["taxa"] for v in trips if v["fim"] is not None)
    print(f"linhas {len(rows)} -> {len(novas)} | resultado local {total(rows):+.2f} -> {total(novas):+.2f} "
          f"| corretora {alvo:+.2f} | sem execucao {sum(r['motivo'].endswith(SEM_PAR) for r in novas)}")
    if "--aplicar" not in args:
        print("nada gravado (use --aplicar)")
        return 0
    copia = path.with_name(f"{path.name}.antes-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    shutil.copy2(path, copia)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, TRADE_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(novas)
    tmp.replace(path)
    print(f"gravado; original em {copia}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
