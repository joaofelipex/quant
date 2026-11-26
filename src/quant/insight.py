"""Leituras para o painel: o que a IA e o robo estao vendo agora, o fluxo de um ativo e os estudos do repositorio.

So le arquivos locais (diario da IA, estado do robo, fotos do livro, README). Sem chave e sem rede.
"""
from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .live import assets as assets_mod

REPO = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[`?([^\]`]+)`?\]\(([^)]+)\)")


def _lines(path: Path, n: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []


def _decisions(path: Path, n: int) -> list[dict]:
    out = []
    for ln in _lines(path, n):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def flow_rows(folder: Path, since: float, asset: str | None = None) -> list[dict]:
    """Fotos do livro desde ``since``, dos arquivos diarios necessarios; linhas quebradas sao ignoradas."""
    day = datetime.fromtimestamp(since, timezone.utc).date()
    out: list[dict] = []
    while day <= datetime.now(timezone.utc).date() + timedelta(days=1):
        try:
            with (folder / f"{day:%Y-%m-%d}.csv").open(newline="") as f:
                for r in csv.DictReader(f):
                    if asset and r.get("asset") != asset:
                        continue
                    try:
                        row = {"asset": r["asset"], "ts": int(r["ts"]), "mid": (float(r["bid"]) + float(r["ask"])) / 2,
                               "spread_bps": float(r["spread_bps"]), "imb_100": float(r["imb_100"]),
                               "imb_25": float(r["imb_25"])}
                    except (KeyError, TypeError, ValueError):
                        continue
                    if row["ts"] >= since:
                        out.append(row)
        except OSError:
            pass
        day += timedelta(days=1)
    return sorted(out, key=lambda r: r["ts"])


def ai_reading(decisions: list[dict], now: float) -> dict | None:
    """O ultimo ciclo da IA em funil: universo, fotos, candidatos com os numeros que ela viu e o destino de cada um."""
    if not decisions:
        return None
    d = decisions[-1]
    acoes = d.get("acoes", [])
    destino = {a.get("ativo"): a for a in acoes}
    leitura = d.get("leitura") or [{"ativo": a} for a in d.get("candidatos", [])]
    linhas = []
    for c in leitura:
        a = destino.get(c.get("ativo"))
        linhas.append({**c, "decisao": a.get("acao") if a else None, "status": a.get("status") if a else None,
                       "porque": (a.get("why") or a.get("motivo") or "") if a else ""})
    ok = sum(a.get("status") in ("executada", "sombra") for a in acoes)
    return {"t": d.get("t"), "ha_s": round(now - d.get("t", now)), "modelo": d.get("model"),
            "sombra": bool(d.get("sombra")), "erro": d.get("erro"), "analise": d.get("analise", ""),
            "funil": {"universo": d.get("universo", 0), "fotos": d.get("fotos", 0), "candidatos": len(linhas),
                      "pedidos": len(acoes), "aceitos": ok},
            "candidatos": linhas, "posicoes": d.get("posicoes", []),
            "historico": [{"t": x.get("t"), "pedidos": len(x.get("acoes", [])),
                           "aceitos": sum(a.get("status") in ("executada", "sombra") for a in x.get("acoes", []))}
                          for x in decisions[-60:]]}


def runner_radar(state_dir: Path, names: list[str], flows: dict[str, dict], er_min: float) -> list[dict]:
    """Para cada ativo do robo: o que a ultima barra mostrou e quanto falta para um rompimento."""
    out = []
    for a in names:
        try:
            st = json.loads((state_dir / f"live_state.{a}.json").read_text())
        except (OSError, ValueError):
            st = {}
        v, risk = st.get("leitura") or {}, st.get("risk") or {}
        close, hi, lo = v.get("close"), v.get("canal_alta"), v.get("canal_baixa")
        up = (hi / close - 1) * 100 if close and hi else None      # quanto falta subir para romper
        down = (close / lo - 1) * 100 if close and lo else None    # quanto falta cair para romper
        out.append({"ativo": a, "barra": st.get("last_bar"), "preco": close, "falta_alta_pct": up,
                    "falta_baixa_pct": down, "er": v.get("er"), "er_ok": v.get("er") is not None and v["er"] >= er_min,
                    "tendencia": v.get("tendencia"), "sinal": v.get("sinal"), "resultado": v.get("resultado"),
                    "posicao": (st.get("entry") or {}).get("side"), "travado": bool(risk.get("halted")),
                    "motivo": risk.get("reason") or "", "fluxo": (flows.get(a) or {}).get("imb_100")})

    def perto(r: dict) -> float:
        d = r["falta_alta_pct"] if r["tendencia"] == 1 else r["falta_baixa_pct"]
        return d if d is not None else 1e9
    return sorted(out, key=lambda r: (r["posicao"] is None, not r["er_ok"], perto(r)))


def live(agent_dir: Path, state_dir: Path, flow_dir: Path, metrics: Path, names: list[str], er_min: float,
         *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    decisions = _decisions(agent_dir / "decisions.jsonl", 60)
    recent = flow_rows(flow_dir, now - 900)
    latest = {r["asset"]: r for r in recent}
    radar = runner_radar(state_dir, names, latest, er_min)

    def age(t: float | None) -> int | None:
        return None if t is None else max(0, round(now - t))

    try:
        coleta = json.loads(metrics.read_text(encoding="utf-8"))["em"]
    except (OSError, ValueError, KeyError):
        coleta = None
    bars = [r["barra"] for r in radar if r["barra"]]
    fontes = [
        {"nome": "fotos do livro", "idade_s": age(max((r["ts"] for r in recent), default=None)), "limite_s": 180,
         "detalhe": f"{len(latest)} ativos nos últimos 15 min"},
        {"nome": "ciclo da IA", "idade_s": age(decisions[-1].get("t") if decisions else None), "limite_s": 900,
         "detalhe": f"{len(decisions)} ciclos carregados"},
        {"nome": "barras do robô", "limite_s": 7500, "detalhe": f"{len(bars)} de {len(names)} ativos",
         "idade_s": age(datetime.fromisoformat(max(bars)).replace(tzinfo=timezone.utc).timestamp() if bars else None)},
        {"nome": "métricas da conta", "idade_s": age(coleta), "limite_s": 360, "detalhe": "corretora"},
    ]
    assets = sorted(set(latest) | set(names))
    return {"em": int(now), "ia": ai_reading(decisions, now), "robo": radar, "er_min": er_min, "fontes": fontes,
            "ativos": assets}


def flow_series(flow_dir: Path, agent_dir: Path, asset: str, hours: float = 6, *, now: float | None = None,
                points: int = 360) -> dict:
    """Preco e desequilibrio do livro de um ativo nas ultimas horas, com as decisoes da IA sobre ele."""
    if asset not in assets_mod.CATALOG:
        raise ValueError(f"ativo invalido: {asset!r}")
    now = time.time() if now is None else now
    since = now - min(max(hours, 0.5), 48) * 3600
    rows = flow_rows(flow_dir, since, asset)
    step = max(1, -(-len(rows) // points))
    marks = [{"t": d["t"], "acao": a.get("acao"), "status": a.get("status"),
              "porque": a.get("why") or a.get("motivo") or ""}
             for d in _decisions(agent_dir / "decisions.jsonl", 600) if d.get("t", 0) >= since
             for a in d.get("acoes", []) if a.get("ativo") == asset]
    return {"ativo": asset, "serie": [[r["ts"], r["mid"], r["imb_100"], r["spread_bps"]] for r in rows[::step]],
            "decisoes": marks[-20:][::-1]}


def research(readme: Path = REPO / "README.md") -> list[dict]:
    """A tabela 'Status da pesquisa' do README: e a fonte unica do veredito de cada estudo."""
    out, dentro = [], False
    for ln in _lines(readme, 10_000):
        if ln.startswith("## "):
            dentro = ln.strip() == "## Status da pesquisa"
            continue
        if not dentro or not ln.startswith("| [") or ln.count("|") < 5:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split(" | ")]
        if len(cells) != 4:
            continue
        m = LINK.search(cells[0])
        clean = [LINK.sub(r"\1", c).replace("**", "").replace("`", "") for c in cells]
        status = clean[3].lower()
        tom = "bad" if "reprovad" in status or "sem edge" in status else "warn"
        out.append({"nome": m.group(1) if m else clean[0], "hipotese": clean[1], "resultado": clean[2],
                    "status": clean[3], "tom": tom})
    return out
