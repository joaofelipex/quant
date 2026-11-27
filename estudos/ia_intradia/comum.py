"""Dados compartilhados do estudo: velas publicas de 1 min da Kalshi DEMO (bid/ask) e o historico da IA copiado da VM.

Velas: baixadas sem chave para ``dados/raw/kalshi_demo_1m/`` (o download retoma de onde parou).
Historico: ``decisions.jsonl`` e ``fills.jsonl`` copiados de /var/lib/quant/{agent,metrics}/
para ``dados/raw/vm_27nov/``.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
from quant import observ  # noqa: E402
from quant.agent import FEE_BPS  # noqa: E402
from quant.live import assets as A  # noqa: E402

VELAS = RAIZ / "dados" / "raw" / "kalshi_demo_1m"
VM = RAIZ / "dados" / "raw" / "vm_27nov"
HOST = "https://external-api.demo.kalshi.co/trade-api/v2/margin/markets"
INI = int(observ.epoch("2026-11-17T00:00:00Z"))
FIM = int(observ.epoch("2026-11-27T12:00:00Z"))
# taxa por lado em bps, de GET /margin/fee_tiers na conta demo (27/11/2026)
TAKER = {"Crypto": 12.0, "Equities": 12.0, "GPU": 12.0, "Metals": 0.72, "Indices": 0.72, "FX": 1.8}
MAKER = {"Crypto": 2.0, "Equities": 2.0, "GPU": 2.0, "Metals": 0.12, "Indices": 0.12, "FX": 0.3}


def _pedir(s: requests.Session, url: str) -> list[dict]:
    for n in range(8):
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200:
                return r.json().get("candlesticks", [])
            if r.status_code != 429 and r.status_code < 500:
                r.raise_for_status()
        except requests.ConnectionError:
            pass
        time.sleep(2 ** min(n, 5))
    raise RuntimeError(f"sem resposta: {url}")


def _baixar(a: str) -> None:
    out = VELAS / f"{a}.csv.gz"
    if out.exists():
        return
    s, rows, t = requests.Session(), [], INI
    while t < FIM:
        for c in _pedir(s, f"{HOST}/{A.ticker(a)}/candlesticks?period_interval=1&start_ts={t}"
                           f"&end_ts={min(t + 300 * 60, FIM)}"):
            try:
                rows.append((c["end_period_ts"], float(c["bid"]["close"]), float(c["ask"]["close"])))
            except (KeyError, TypeError, ValueError):
                pass
        t += 300 * 60
    pd.DataFrame(rows, columns=["ts", "bid", "ask"]).drop_duplicates("ts").to_csv(out, index=False)


def baixar() -> None:
    VELAS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(_baixar, list(A.CATALOG)))


def velas():
    """(bid, ask, mid, idx em minutos, classe por ativo, taxa taker por ativo), so cotacao executavel e sem picos."""
    idx = np.arange(INI // 60, FIM // 60 + 1)
    bid, ask = {}, {}
    for a in A.CATALOG:
        p = VELAS / f"{a}.csv.gz"
        if not p.exists():
            continue
        d = pd.read_csv(p)
        if len(d) < 500:
            continue
        d.index = d.ts // 60
        d = d[~d.index.duplicated()]
        d = d[(d.bid > 0) & (d.ask >= d.bid) & ((d.ask / d.bid - 1) < 0.005)]  # spread < 50 bps
        bid[a], ask[a] = d.bid.reindex(idx), d.ask.reindex(idx)
    bid, ask = pd.DataFrame(bid), pd.DataFrame(ask)
    mid = (bid + ask) / 2
    bom = (mid / mid.rolling(11, center=True, min_periods=3).median() - 1).abs() < 0.03  # picos falsos da demo
    bid, ask, mid = bid.where(bom), ask.where(bom), mid.where(bom)
    cls = {a: A.CATALOG[a]["cls"] for a in mid}
    fee = {a: FEE_BPS.get(cls[a], 12) for a in mid}
    return bid, ask, mid, idx, cls, fee


def operacoes_ia() -> tuple[list[dict], list[dict]]:
    """(posicoes da IA encerradas, execucoes) pelos registros da corretora."""
    fills = observ._jsonl(VM / "fills.jsonl")
    dec = observ._jsonl(VM / "decisions.jsonl")
    trips = [v for v in observ.round_trips(fills, observ.ai_opens(dec)) if v["quem"] == "ia" and v["fim"]]
    return trips, fills


def t_blocos(valores: pd.Series, blocos: pd.Series) -> float:
    """t da media com um ponto por bloco de tempo (ativos andam juntos; cada operacao nao e independente)."""
    b = valores.groupby(blocos).mean()
    return b.mean() / (b.std() / np.sqrt(len(b))) if len(b) > 4 else float("nan")
