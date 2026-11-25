"""Leitura de fluxo: grava o desequilibrio do livro de ofertas da Kalshi e mede se ele antecipa o preco.

    python -m quant.flow record          # uma rodada: 1 consulta publica por ativo -> flow/AAAA-MM-DD.csv
    python -m quant.flow study [pasta]   # junta as fotos ao retorno futuro: o desequilibrio tem poder preditivo?

Por que gravar antes de usar: a Kalshi so mostra o livro de AGORA (sem historico do livro nem de quem agrediu em cada
negocio). A unica forma honesta de saber se "ler fluxo" ajuda na entrada e juntar fotos por alguns dias e medir,
descontando o custo (spread). So depois disso o desequilibrio vira filtro de entrada. Nada aqui manda ordem nem usa
chave: so leitura publica.

Desequilibrio = (profundidade de compra - de venda) / soma, em USD, dentro de uma faixa em torno do preco do meio.
Ignora ofertas soltas longe do mercado (como o ask perdido que causou o fill absurdo em ALUMINUM). Vai de -1 (so venda)
a +1 (so compra).
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .live import assets as assets_mod
from .live.http import get_json

log = logging.getLogger("quant.flow")

HOST = "https://external-api.demo.kalshi.co/trade-api/v2/margin/markets"
FLOW_DIR = Path("/var/lib/quant/flow")
BANDS = (0.0025, 0.01)  # faixas em torno do meio: 0,25% e 1%
FIELDS = ["ts", "asset", "mark", "bid", "ask", "spread_bps", "imb_25", "imb_100", "imb_top5", "bid_usd_100",
          "ask_usd_100"]

Levels = list[tuple[float, float]]


def _levels(raw: list | None) -> Levels:
    out: Levels = []
    for lv in raw or []:
        try:
            out.append((float(lv[0]), float(lv[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _imbalance(bids: Levels, asks: Levels, mid: float, band: float) -> tuple[float, float, float]:
    """(desequilibrio, USD de compra, USD de venda) dentro de ``band`` em torno de ``mid``."""
    b = sum(p * q for p, q in bids if p >= mid * (1 - band))
    a = sum(p * q for p, q in asks if p <= mid * (1 + band))
    return ((b - a) / (b + a) if b + a > 0 else 0.0), b, a


def features(book: dict, mark: float) -> dict | None:
    """Foto do livro -> medidas de fluxo. None se o livro estiver vazio ou longe do preco justo."""
    bids = sorted(_levels(book.get("bids")), reverse=True)
    asks = sorted(_levels(book.get("asks")))
    if not bids or not asks:
        return None
    bid, ask = bids[0][0], asks[0][0]
    mid = (bid + ask) / 2
    if mid <= 0 or abs(mid / mark - 1) > 0.05:  # oferta solta: foto inutil
        return None
    imb25, _, _ = _imbalance(bids, asks, mid, BANDS[0])
    imb100, b100, a100 = _imbalance(bids, asks, mid, BANDS[1])
    t5b, t5a = sum(p * q for p, q in bids[:5]), sum(p * q for p, q in asks[:5])
    return {"mark": mark, "bid": bid, "ask": ask, "spread_bps": (ask - bid) / mid * 1e4, "imb_25": imb25,
            "imb_100": imb100, "imb_top5": (t5b - t5a) / (t5b + t5a) if t5b + t5a > 0 else 0.0,
            "bid_usd_100": b100, "ask_usd_100": a100}


def snapshot_one(asset: str, fetch=get_json) -> dict | None:
    tk = assets_mod.ticker(asset)
    try:
        mark = float(fetch(f"{HOST}/{tk}")["market"]["price"])
        book = fetch(f"{HOST}/{tk}/orderbook")["orderbook"]
        f = features(book, mark)
    except Exception:  # noqa: BLE001 - um ativo fora do ar nao pode perder a rodada dos outros
        log.exception("sem foto do livro de %s", asset)
        return None
    return None if f is None else {"asset": asset, **f}


def record(names: list[str], out_dir: Path = FLOW_DIR, *, fetch=get_json, now=time.time, workers: int = 12) -> int:
    """Uma rodada: foto de cada ativo em paralelo, acrescentada ao CSV do dia. Devolve quantas linhas gravou."""
    ts = int(now())
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(names)))) as pool:
        rows = [r for r in pool.map(lambda a: snapshot_one(a, fetch), names) if r]
    if not rows:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{datetime.fromtimestamp(ts, timezone.utc):%Y-%m-%d}.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({"ts": ts, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}})
    return len(rows)


# ---- estudo ---------------------------------------------------------------------------------------------------------
def load(folder: Path) -> pd.DataFrame:
    parts = [pd.read_csv(f) for f in sorted(folder.glob("*.csv"))]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=FIELDS)


def with_forward_returns(df: pd.DataFrame, horizons=(1, 5, 15)) -> pd.DataFrame:
    """Acrescenta ``ret_<h>m`` (bps, do meio agora ate o meio ``h`` min depois) por ativo; sem futuro = NaN."""
    df = df.sort_values(["asset", "ts"]).copy()
    df["mid"] = (df["bid"] + df["ask"]) / 2
    for h in horizons:
        fut = df.groupby("asset")["mid"].shift(-h)
        gap = df.groupby("asset")["ts"].shift(-h) - df["ts"]
        ok = (gap >= h * 60 - 30) & (gap <= h * 60 + 30)  # so conta se a foto futura veio no minuto certo
        df[f"ret_{h}m"] = ((fut / df["mid"] - 1) * 1e4).where(ok)
    return df


def evaluate(df: pd.DataFrame, feature: str = "imb_100", horizons=(1, 5, 15)) -> dict:
    """Poder preditivo de ``feature`` sobre o retorno futuro: correlacao de postos (IC), retorno medio por quintil e o
    que sobra de 'compra o quintil de cima, vende o de baixo' depois do custo (um spread). So dados, sem opiniao."""
    d = with_forward_returns(df, horizons)
    dias = round((d["ts"].max() - d["ts"].min()) / 86400, 2) if len(d) else 0.0
    out: dict = {"fotos": len(d), "ativos": int(d["asset"].nunique()), "dias": dias, "horizontes": {}}
    for h in horizons:
        x = d[[feature, f"ret_{h}m", "spread_bps"]].dropna()
        if len(x) < 50 or x[feature].nunique() < 5:
            out["horizontes"][h] = {"n": len(x), "ic": None, "veredito": "poucos dados"}
            continue
        ic = float(x[feature].rank().corr(x[f"ret_{h}m"].rank()))
        q = pd.qcut(x[feature].rank(method="first"), 5, labels=False)
        by = x.groupby(q)[f"ret_{h}m"].mean()
        spread = float(x["spread_bps"].mean())
        long_short = float(by.iloc[-1] - by.iloc[0])  # bps por trade, antes do custo
        net = long_short - spread
        z = ic * (len(x) ** 0.5)  # aproximacao: sob a hipotese nula, IC ~ N(0, 1/sqrt(n))
        out["horizontes"][h] = {
            "n": len(x), "ic": round(ic, 4), "z": round(z, 2), "quintis_bps": [round(float(v), 3) for v in by],
            "spread_medio_bps": round(spread, 2), "long_short_bps": round(long_short, 3), "liquido_bps": round(net, 3),
            "veredito": "tem sinal apos custo" if (abs(z) > 3 and net > 0) else "sem vantagem comprovada"}
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args and args[0] == "record":
        spec = os.environ.get("QUANT_FLOW_ASSETS") or os.environ.get("QUANT_ASSETS") or "tudo"
        names = assets_mod.parse(spec)
        n = record(names, Path(os.environ.get("QUANT_FLOW_DIR", str(FLOW_DIR))))
        print(f"{n}/{len(names)} fotos gravadas")
        return 0 if n else 1
    if args and args[0] == "study":
        df = load(Path(args[1] if len(args) > 1 else os.environ.get("QUANT_FLOW_DIR", str(FLOW_DIR))))
        if df.empty:
            print("sem fotos ainda: deixe o gravador rodar")
            return 1
        for feat in ("imb_100", "imb_25", "imb_top5"):
            r = evaluate(df, feat)
            print(f"\n== {feat}: {r['fotos']} fotos, {r['ativos']} ativos, {r['dias']} dia(s)")
            for h, v in r["horizontes"].items():
                print(f"  {h:>2} min  n={v['n']:<7} IC={v.get('ic')}  z={v.get('z')}  "
                      f"liquido={v.get('liquido_bps')} bps  -> {v['veredito']}")
        return 0
    print("uso: python -m quant.flow record | study [pasta]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
