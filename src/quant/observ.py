"""Observabilidade: junta o que a CORRETORA registrou com o estado local e grava um retrato para o painel.

    python -m quant.observ            # unit quant-metrics (timer), com a chave; o processo web so le o arquivo

So faz leitura (GET). Saidas em QUANT_METRICS_DIR: ``metrics.json`` (retrato atual), ``equity.jsonl`` (um ponto por
coleta) e ``fills.jsonl`` (execucoes ja baixadas, para nao pedir o historico inteiro toda vez).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .live import assets as assets_mod

log = logging.getLogger("quant.observ")

METRICS_DIR = Path("/var/lib/quant/metrics")
UNITS = {"quant-live.service": "robô de regras", "quant-control.service": "painel", "quant-agent.timer": "IA (timer)",
         "quant-flow.timer": "foto do livro", "quant-metrics.timer": "métricas", "quant-selfcheck.timer": "autoteste",
         "quant-alert.timer": "alertas"}
MATCH_S = 240        # uma abertura e da IA se o diario dela registrou o mesmo ativo a ate isto de distancia
EQUITY_POINTS = 600  # pontos enviados ao painel


def epoch(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def asset_of(ticker: str) -> str:
    for a, v in assets_mod.CATALOG.items():
        if v["ticker"] == ticker:
            return a
    return ticker


def ai_opens(decisions: list[dict]) -> list[tuple[str, float]]:
    return [(a["ativo"], d["t"]) for d in decisions for a in d.get("acoes", [])
            if a.get("acao") == "abrir" and a.get("status") == "executada"]


def round_trips(fills: list[dict], opens: list[tuple[str, float]]) -> list[dict]:
    """Agrupa execucoes em posicoes (de zerado a zerado), com resultado, taxas e quem abriu."""
    out, aberta = [], {}
    for f in sorted(fills, key=lambda f: epoch(f["created_time"])):
        t, ts = f["ticker"], epoch(f["created_time"])
        v = aberta.get(t)
        if v is None:
            a = asset_of(t)
            quem = "ia" if any(x == a and abs(ts - quando) <= MATCH_S for x, quando in opens) else "robo"
            v = aberta[t] = {"asset": a, "ticker": t, "quem": quem, "q": 0.0, "bruto": 0.0, "taxa": 0.0, "ini": ts,
                             "fim": None, "corretora": False, "lado": 1 if f["side"] == "bid" else -1}
        v["q"] = round(v["q"] + float(f["count"]) * (1 if f["side"] == "bid" else -1), 4)
        v["bruto"] += float(f.get("realized_pnl") or 0)
        v["taxa"] += float(f.get("fees") or 0)
        v["corretora"] |= f.get("order_source") == "system"  # stop/liquidacao executado pela corretora
        if abs(v["q"]) < 1e-6:
            v["fim"] = ts
            out.append(aberta.pop(t))
    return out + list(aberta.values())


def group(trips: list[dict], key) -> list[dict]:
    g: dict = defaultdict(list)
    for v in trips:
        g[key(v)].append(v)
    out = []
    for k, vs in sorted(g.items()):
        bruto, taxa = sum(v["bruto"] for v in vs), sum(v["taxa"] for v in vs)
        fechadas = [v for v in vs if v["fim"] is not None]
        out.append({"nome": k, "posicoes": len(vs), "fechadas": len(fechadas),
                    "ganhos": sum(v["bruto"] > v["taxa"] for v in fechadas), "bruto": round(bruto, 4),
                    "taxa": round(taxa, 4), "liquido": round(bruto - taxa, 4)})
    return out


def shadow_stats(decisions: list[dict]) -> dict:
    ciclos = [d for d in decisions if d.get("sombra")]
    fechadas = [{"t": d["t"], "asset": a.get("ativo"), "bps": a["liquido_bps"]}
                for d in ciclos for a in d.get("acoes", []) if "liquido_bps" in a]
    abertas = sum(1 for d in ciclos for a in d.get("acoes", [])
                  if a.get("status") == "sombra" and a.get("acao") == "abrir")
    vals = [x["bps"] for x in fechadas]
    return {"ciclos": len(ciclos), "abertas": abertas, "fechadas": len(vals), "ganhos": sum(v > 0 for v in vals),
            "media_bps": round(sum(vals) / len(vals), 1) if vals else None, "total_bps": round(sum(vals), 1),
            "ultimas": fechadas[-12:][::-1]}


def agent_stats(decisions: list[dict], now: float) -> dict:
    recentes = [d for d in decisions if now - d["t"] <= 86400]
    recusas = Counter(str(a.get("why", "")).split(" (")[0][:70] for d in recentes for a in d.get("acoes", [])
                      if a.get("status") == "recusada")
    return {"ciclos_24h": len(recentes), "erros_24h": sum(bool(d.get("erro")) for d in recentes),
            # mercado fechado nao e falha do sistema (o agente deixou de tentar); o resto conta
            "falhas_24h": sum(a.get("status") == "falhou" and "market_inactive" not in str(a.get("detalhe", ""))
                              for d in recentes for a in d.get("acoes", [])),
            "ultimo_ciclo_s": round(now - decisions[-1]["t"]) if decisions else None,
            "ultima_analise": decisions[-1].get("analise", "") if decisions else "",
            "recusas": [{"motivo": m, "n": n} for m, n in recusas.most_common(6)]}


def problems(snap: dict) -> list[dict]:
    """O que precisa de atencao agora, do mais grave ao menos."""
    out: list[dict] = []

    def add(nivel: str, texto: str) -> None:
        out.append({"nivel": nivel, "texto": texto})

    for p in snap["posicoes"]:
        if p["stop"] is False:
            add("bad", f"{p['asset']}: posição aberta SEM stop na corretora")
    for s in snap["servicos"]:
        if s["estado"] != "active":
            estado = {"inactive": "parado", "failed": "com falha"}.get(s["estado"], s["estado"])
            add("bad", f"serviço {s['nome']}: {estado}")
    if snap["kill"]:
        add("bad", "kill-switch acionado: nada abre até removê-lo")
    ia = snap["ia"]
    if ia["ligada"] and (ia["ultimo_ciclo_s"] is None or ia["ultimo_ciclo_s"] > ia["intervalo_min"] * 180):
        add("bad", "IA ligada, mas sem ciclo recente")
    if ia["erros_24h"]:
        add("warn", f"IA: {ia['erros_24h']} ciclo(s) com erro em 24 h")
    if ia["falhas_24h"]:
        add("warn", f"IA: {ia['falhas_24h']} ordem(ns) falharam em 24 h")
    if snap["travados"]:
        add("warn", "robô travado em: " + ", ".join(f"{x['asset']} ({x['motivo']})" for x in snap["travados"][:8]))
    c = snap["conta"]
    if c["disponivel"] is not None and c["disponivel"] <= 0:
        add("warn", "a corretora informa saldo disponível zero")
    dif = snap["registro"]["diferenca"]
    if abs(dif) >= 1:
        add("warn", f"registro local difere da corretora em US$ {dif:+.2f}".replace(".", ","))
    return sorted(out, key=lambda p: p["nivel"] != "bad")


def snapshot(*, fills: list[dict], balance: dict, positions: list[dict], funding: list[dict], stops: dict[str, bool],
             decisions: list[dict], agent_cfg: dict, local_pnl: float, services: list[dict], runner: list[dict],
             kill: bool, equity: list[list], now: float) -> dict:
    trips = round_trips(fills, ai_opens(decisions))
    aberto = sum(float(p.get("unrealized_pnl") or 0) for p in positions)
    bruto = sum(v["bruto"] for v in trips)
    taxa = sum(v["taxa"] for v in trips)
    fund = sum(float(x["funding_amount"]) for x in funding)
    liquido = bruto - taxa + fund + aberto
    sub = (balance.get("subaccount_balances") or [{}])[0]
    eq = float(sub.get("account_equity") or 0)
    donos = {v["ticker"]: v["quem"] for v in trips if v["fim"] is None}
    pos = [{"asset": asset_of(p["market_ticker"]), "quem": donos.get(p["market_ticker"], "?"),
            "qtd": float(p["position"]), "entrada": float(p.get("entry_price") or 0),
            "aberto": float(p.get("unrealized_pnl") or 0), "stop": stops.get(p["market_ticker"])}
           for p in positions if float(p.get("position") or 0)]
    fechadas = [v for v in trips if v["fim"] is not None]
    realizado = sum(v["bruto"] - v["taxa"] for v in fechadas)  # o registro local so tem posicoes encerradas
    snap = {
        "em": int(now),
        "conta": {"patrimonio": eq,
                  "disponivel": float(sub["available_balance"]) if "available_balance" in sub else None,
                  "inicial_implicito": round(eq - liquido, 2), "liquido": round(liquido, 4), "bruto": round(bruto, 4),
                  "taxas": round(taxa, 4), "funding": round(fund, 4), "aberto": round(aberto, 4),
                  "execucoes": len(fills)},
        "por_origem": group(trips, lambda v: v["quem"]),
        "por_classe": group(trips, lambda v: (assets_mod.CATALOG.get(v["asset"]) or {}).get("cls", "?")),
        "por_dia": group(trips, lambda v: day(v["fim"] or now)),
        "extremos": [{"asset": v["asset"], "quem": v["quem"], "liquido": round(v["bruto"] - v["taxa"], 4),
                      "em": int(v["fim"]), "corretora": v["corretora"]}
                     for v in sorted(fechadas, key=lambda v: -abs(v["bruto"] - v["taxa"]))[:8]],
        "posicoes": pos,
        "registro": {"local": round(local_pnl, 4), "corretora": round(realizado, 4),
                     "diferenca": round(local_pnl - realizado, 2)},
        "ia": {"ligada": bool(agent_cfg.get("enabled")), "sombra": bool(agent_cfg.get("shadow")),
               "intervalo_min": agent_cfg.get("interval_min", 10), "modelo": agent_cfg.get("model", ""),
               **agent_stats(decisions, now)},
        "sombra": shadow_stats(decisions),
        "servicos": services,
        "travados": [{"asset": r["asset"], "motivo": r["reason"]} for r in runner if r["halted"]],
        "kill": kill,
        "equity": equity[-EQUITY_POINTS:],
    }
    snap["problemas"] = problems(snap)
    return snap


# ---- cola com o mundo real ------------------------------------------------------------------------------------------
def _jsonl(path: Path) -> list:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def pages(ex, path: str, key: str, **params) -> list[dict]:
    out, cursor = [], ""
    while True:
        r = ex._req("GET", path, params={**params, **({"cursor": cursor} if cursor else {})})
        got = r.get(key) or []
        out += got
        cursor = r.get("cursor") or ""
        if not cursor or not got:
            return out


def sync_fills(ex, path: Path) -> list[dict]:
    """Baixa so o que falta (com 10 min de folga) e junta por ``fill_id``."""
    known = {f["fill_id"]: f for f in _jsonl(path)}
    params = {"limit": 1000}
    if known:
        params["min_ts"] = int(max(epoch(f["created_time"]) for f in known.values())) - 600
    new = [f for f in pages(ex, "/margin/fills", "fills", **params) if f["fill_id"] not in known]
    if new:
        with path.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(x) + "\n" for x in new)
    return list(known.values()) + new


def unit_states() -> list[dict]:
    out = []
    for unit, nome in UNITS.items():
        r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10)
        out.append({"unit": unit, "nome": nome, "estado": r.stdout.strip() or "desconhecido"})
    return out


def collect(env=os.environ.get, now: float | None = None) -> dict:
    from . import agent, control
    from .live.config import build_kalshi

    if env("QUANT_MODE") != "testnet" or env("QUANT_VENUE") != "kalshi":
        raise SystemExit("metricas: so com a Kalshi demo (QUANT_VENUE=kalshi, QUANT_MODE=testnet)")
    now = time.time() if now is None else now
    out_dir = Path(env("QUANT_METRICS_DIR", str(METRICS_DIR)))
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir = Path(env("QUANT_STATE", "/var/lib/quant/live_state.json")).parent
    agent_dir = Path(env("QUANT_AGENT_DIR", str(agent.AGENT_DIR)))
    ex = build_kalshi("testnet", env, assets_mod.ticker("BTC"))

    fills = sync_fills(ex, out_dir / "fills.jsonl")
    # sem o parametro a Kalshi devolve saldo disponivel sempre zero
    balance = ex._req("GET", "/margin/balance", params={"compute_available_balance": "true"})
    positions = ex._req("GET", "/margin/positions").get("positions", [])
    start = day(min((epoch(f["created_time"]) for f in fills), default=now))
    funding = ex._req("GET", "/margin/funding_history",
                      params={"start_date": start, "end_date": day(now)}).get("funding_history") or []
    stops: dict[str, bool] = {}
    for p in positions:
        t = p["market_ticker"]
        if float(p.get("position") or 0):
            try:
                triggers = ex._req("GET", f"/margin/{ex.mode}/positions/{t}/exit_trigger").get("exit_triggers", [])
                stops[t] = any(x.get("stop_loss_price") and x.get("status") in ("active", "pending_on_entry")
                               for x in triggers)
            except Exception:  # noqa: BLE001 - sem resposta: fica "nao sei", nao "sem stop"
                log.exception("sem o stop de %s", t)
    local = control.trades_summary(Path(env("QUANT_TRADES_LOG", "/var/lib/quant/trades.csv")), 10**9)
    runtime = control.read_runtime(Path(env("QUANT_RUNTIME_ENV", "/var/lib/quant/runtime.env")))
    names = [a for a in runtime.get("QUANT_ASSETS", "").split(",") if a in assets_mod.CATALOG]

    eq = float((balance.get("subaccount_balances") or [{}])[0].get("account_equity") or 0)
    history = out_dir / "equity.jsonl"
    with history.open("a", encoding="utf-8") as f:
        f.write(json.dumps([int(now), eq]) + "\n")

    snap = snapshot(fills=fills, balance=balance, positions=positions, funding=funding, stops=stops,
                    decisions=_jsonl(agent_dir / "decisions.jsonl"),
                    agent_cfg=agent.load_config(agent_dir / "config.json"),
                    local_pnl=sum(t["pnl"] for t in local["trades"] if t["origem"].startswith("kalshi")),
                    services=unit_states(), runner=control.assets_summary(state_dir, names, now),
                    kill=Path(env("QUANT_KILL_FILE", "/var/lib/quant/KILL")).exists(), equity=_jsonl(history), now=now)
    tmp = out_dir / "metrics.tmp"
    tmp.write_text(json.dumps(snap), encoding="utf-8")
    tmp.replace(out_dir / "metrics.json")
    return snap


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    snap = collect()
    log.info("patrimonio %.2f | liquido %.2f | %d problema(s)", snap["conta"]["patrimonio"], snap["conta"]["liquido"],
             len(snap["problemas"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
