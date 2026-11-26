"""Agente de IA que opera na VM (SO na Kalshi DEMO): olha o mercado, decide com o Claude e executa como a Boleta.

    python -m quant.agent run [--force]    # um ciclo (o timer chama a cada minuto; o intervalo vem da configuracao)
    python -m quant.agent status

Como funciona, e onde esta a seguranca:
  1. ``snapshot``: fotos do livro de ofertas de todo o universo + velas dos candidatos + posicoes reais na corretora.
  2. O Claude recebe so numeros nossos (nada de texto da internet: sem injecao de prompt) e responde pela ferramenta
     ``decide`` com ate N acoes (abrir/fechar), cada uma com motivo.
  3. ``validate``: as TRAVAS estao no codigo, nao no prompt. O modelo pode pedir qualquer coisa; so passa o que cabe nos
     limites (valor maximo, posicoes, stop obrigatorio, perda do dia, cooldown, long-only, kill-switch, so demo).
  4. A execucao usa ``manual.execute`` (a mesma da Boleta): ordem a mercado, stop na corretora e historico de
     trades. Se a posicao abrir SEM stop, o agente a fecha na hora.
  5. Tudo vai para ``decisions.jsonl`` e para a auditoria do painel. A chave da IA fica em /etc/quant/agent.env,
     que voce grava na VM; o painel nunca a le.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .live import assets as assets_mod

log = logging.getLogger("quant.agent")

AGENT_DIR = Path("/var/lib/quant/agent")
API_URL = "https://api.anthropic.com/v1/messages"
MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5")

DEFAULTS: dict = {
    "enabled": False,          # desligada ate alguem ligar no painel
    "model": "claude-sonnet-5-5",
    "interval_min": 10,        # minutos entre ciclos (cada ciclo = 1 chamada ao modelo)
    "max_usd": 15.0,           # valor maximo por entrada
    "max_positions": 5,        # posicoes abertas ao mesmo tempo (as do agente)
    "max_daily_loss": 2.0,     # USD: ao perder isso no dia (UTC) o agente para de ABRIR (e se desliga)
    "long_only": True,         # so comprado
    "stop_min": 0.5,           # stop obrigatorio, em % do preco de entrada
    "stop_max": 5.0,
    "cooldown_min": 20,        # depois de fechar um ativo, espera isto para reabrir
    "max_actions": 3,          # acoes por ciclo
    "max_hold_h": 24,          # fecha a posicao que passar deste tempo
    "candidates": 12,          # ativos com analise detalhada por ciclo
    "universe": "tudo",        # "tudo", "todos" (20 cripto) ou lista: BTC,NVDA,...
    "edge_min": 2.0,           # o alvo da entrada precisa cobrir N vezes o custo de entrar e sair (0 desliga)
}

# taxa por lado em bps, medida nas execucoes da Kalshi demo de 24 a 26/11/2026 (valor tipico mais alto de cada classe)
FEE_BPS = {"Crypto": 12.0, "Equities": 12.0, "FX": 2.3, "Metals": 1.1, "Indices": 0.8}
FEE_BPS_DEFAULT = 12.0         # classe nao medida: assume a mais cara


def round_trip_bps(asset: str, spread_bps: float) -> float:
    """Custo de entrar e sair: as duas taxas mais um spread inteiro."""
    cls = (assets_mod.CATALOG.get(asset) or {}).get("cls")
    return 2 * FEE_BPS.get(cls, FEE_BPS_DEFAULT) + spread_bps


# ---- configuracao ---------------------------------------------------------------------------------------------------
class ConfigError(ValueError):
    pass


def _num(v, name: str, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ConfigError(f"{name} deve ser um numero") from None
    if isinstance(v, bool) or not (lo <= x <= hi) or x != x:
        raise ConfigError(f"{name} deve estar entre {lo:g} e {hi:g}")
    return x


def validate_config(updates: dict) -> dict:
    """Valida e normaliza um pedido de mudanca de configuracao. Levanta ConfigError sem gravar nada."""
    unknown = set(updates) - set(DEFAULTS)
    if unknown:
        raise ConfigError(f"parametro nao permitido: {', '.join(sorted(unknown))}")
    out: dict = {}
    for k, v in updates.items():
        if k in ("enabled", "long_only"):
            if not isinstance(v, bool):
                raise ConfigError(f"{k} deve ser verdadeiro ou falso")
            out[k] = v
        elif k == "model":
            if v not in MODELS:
                raise ConfigError(f"modelo invalido (use um de {', '.join(MODELS)})")
            out[k] = v
        elif k == "universe":
            word = str(v).strip().lower()
            try:
                out[k] = word if word in ("tudo", "todos") else ",".join(assets_mod.parse(str(v)))
            except ValueError as e:
                raise ConfigError(str(e)) from None
            if not out[k]:
                raise ConfigError("universo vazio")
        elif k in ("interval_min", "max_positions", "max_actions", "candidates", "cooldown_min"):
            lo, hi = {"interval_min": (1, 240), "max_positions": (1, 20), "max_actions": (1, 6), "candidates": (4, 30),
                      "cooldown_min": (0, 1440)}[k]
            out[k] = int(_num(v, k, lo, hi))
        else:  # max_usd, max_daily_loss, stop_min, stop_max, max_hold_h, edge_min
            lo, hi = {"max_usd": (1, 100), "max_daily_loss": (0.1, 100), "stop_min": (0.1, 20), "stop_max": (0.2, 30),
                      "max_hold_h": (0.25, 168), "edge_min": (0, 10)}[k]
            out[k] = _num(v, k, lo, hi)
    return out


def load_config(path: Path) -> dict:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    cfg = dict(DEFAULTS)
    try:
        cfg.update(validate_config({k: v for k, v in saved.items() if k in DEFAULTS}))
    except ConfigError:
        log.exception("configuracao do agente invalida; usando os padroes seguros")
    if cfg["stop_min"] > cfg["stop_max"]:
        cfg["stop_min"], cfg["stop_max"] = DEFAULTS["stop_min"], DEFAULTS["stop_max"]
    return cfg


def save_config(path: Path, updates: dict) -> dict:
    clean = validate_config(updates)
    cur = load_config(path)
    cur.update(clean)
    if cur["stop_min"] > cur["stop_max"]:
        raise ConfigError("stop_min nao pode passar de stop_max")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1))
    tmp.replace(path)
    return cur


# ---- travas (codigo, nao prompt) ------------------------------------------------------------------------------------
@dataclass
class Ctx:
    """O que o validador precisa saber do mundo naquele instante."""
    universe: set[str]
    held: dict[str, dict]                    # ativo -> {side, ...} (posicoes reais, ja sem as do runner)
    runner_assets: set[str] = field(default_factory=set)
    runner_active: bool = False
    kill: bool = False
    mode_ok: bool = True                     # kalshi + testnet
    pnl_today: float = 0.0                   # PnL realizado hoje das trades do agente
    last_close: dict[str, float] = field(default_factory=dict)  # ativo -> epoch do ultimo fechamento do agente
    now: float = 0.0
    costs: dict[str, dict] = field(default_factory=dict)  # ativo -> {cost_bps, move_bps (oscilacao tipica de 1 h)}


def edge_refusal(a: dict, ctx: Ctx, cfg: dict) -> str | None:
    """Motivo para recusar uma abertura que nao paga os custos; None se passa."""
    if cfg["edge_min"] <= 0:
        return None
    c = ctx.costs.get(a["ativo"])
    if not c or c.get("move_bps") is None:
        return "sem dados de custo e volatilidade desse ativo neste ciclo"
    need = cfg["edge_min"] * c["cost_bps"] / 100  # em %
    try:
        target = float(a.get("alvo_pct"))
    except (TypeError, ValueError):
        return "alvo_pct (ganho esperado em %) e obrigatorio"
    if not target >= need:
        return f"alvo de {target:g}% nao cobre {cfg['edge_min']:g}x o custo (minimo {need:.2f}%)"
    if c["move_bps"] / 100 < need:
        return f"ativo oscila ~{c['move_bps'] / 100:.2f}% por hora, menos que os {need:.2f}% para pagar o custo"
    return None


def validate(actions: list, ctx: Ctx, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Devolve (aceitas, recusadas). Cada recusada leva ``why``. Nada do que o modelo diz escapa destes limites."""
    ok: list[dict] = []
    bad: list[dict] = []
    held = set(ctx.held)
    n_open = len(held)

    def refuse(a, why):
        keys = ("acao", "ativo", "lado", "usd", "stop_pct", "alvo_pct", "motivo")
        bad.append({**{k: a.get(k) for k in keys}, "why": why})

    if not isinstance(actions, list):
        return [], [{"why": "acoes invalidas (nao e uma lista)"}]
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            bad.append({"why": "acao invalida"})
            continue
        asset = str(a.get("ativo", "")).strip().upper()
        a = {**a, "ativo": asset}
        kind = a.get("acao")
        if i >= cfg["max_actions"]:
            refuse(a, f"acima do maximo de {cfg['max_actions']} acoes por ciclo")
        elif ctx.kill:
            refuse(a, "kill-switch acionado")
        elif not ctx.mode_ok:
            refuse(a, "so opera em Kalshi demo (testnet)")
        elif asset not in ctx.universe:
            refuse(a, "ativo fora do universo do agente")
        elif ctx.runner_active and asset in ctx.runner_assets:
            refuse(a, "ativo operado pelo runner agora")
        elif kind == "fechar":
            if asset not in held:
                refuse(a, "nao ha posicao aberta nesse ativo")
            else:
                ok.append({"acao": "fechar", "ativo": asset, "motivo": str(a.get("motivo", ""))[:200]})
                held.discard(asset)
                n_open -= 1
        elif kind == "abrir":
            side = {"comprado": 1, "vendido": -1}.get(a.get("lado"))
            try:
                usd = float(a.get("usd"))
                stop = float(a.get("stop_pct"))
            except (TypeError, ValueError):
                refuse(a, "valor e stop numericos sao obrigatorios")
                continue
            if side is None:
                refuse(a, "lado deve ser comprado ou vendido")
            elif side < 0 and cfg["long_only"]:
                refuse(a, "agente so opera comprado (long_only)")
            elif ctx.pnl_today <= -cfg["max_daily_loss"]:
                refuse(a, f"perda do dia ({ctx.pnl_today:.2f}) atingiu o limite de {cfg['max_daily_loss']:.2f}")
            elif asset in held:
                refuse(a, "ja existe posicao nesse ativo")
            elif n_open >= cfg["max_positions"]:
                refuse(a, f"limite de {cfg['max_positions']} posicoes abertas")
            elif not (usd > 0) or usd != usd:
                refuse(a, "valor deve ser positivo")
            elif not (cfg["stop_min"] <= stop <= cfg["stop_max"]):
                refuse(a, f"stop deve ficar entre {cfg['stop_min']}% e {cfg['stop_max']}%")
            elif ctx.now - ctx.last_close.get(asset, 0.0) < cfg["cooldown_min"] * 60:
                refuse(a, f"cooldown de {cfg['cooldown_min']} min depois de fechar esse ativo")
            elif why := edge_refusal(a, ctx, cfg):
                refuse(a, why)
            else:
                ok.append({"acao": "abrir", "ativo": asset, "side": side, "usd": min(usd, cfg["max_usd"]),
                           "stop_pct": stop, "alvo_pct": a.get("alvo_pct"), "motivo": str(a.get("motivo", ""))[:200],
                           "ajustado": usd > cfg["max_usd"]})
                held.add(asset)
                n_open += 1
        else:
            refuse(a, "acao desconhecida (use abrir ou fechar)")
    return ok, bad


# ---- instantaneo e prompt -------------------------------------------------------------------------------------------
def pick_candidates(rows: list[dict], held: set[str], k: int, max_usd: float) -> list[str]:
    """Os ``k`` ativos de maior |desequilibrio| com spread razoavel e livro com dinheiro, mais os ja abertos."""
    ok = [r for r in rows if r["spread_bps"] <= 30 and min(r["bid_usd_100"], r["ask_usd_100"]) >= max_usd * 50]
    ok.sort(key=lambda r: abs(r["imb_100"]), reverse=True)
    out = [a for a in held if any(r["asset"] == a for r in rows)]
    for r in ok:
        if len(out) >= k + len(held):
            break
        if r["asset"] not in out:
            out.append(r["asset"])
    return out


def candle_features(bars) -> dict | None:
    """Retornos (bps) em 5/15/60 min e volatilidade de 1 min, das barras de 1 min ja fechadas."""
    if bars is None or len(bars) < 20:
        return None
    c = [float(x) for x in bars["close"]]

    def ret(n: int) -> float | None:
        return round((c[-1] / c[-1 - n] - 1) * 1e4, 1) if len(c) > n and c[-1 - n] > 0 else None

    rets = [(c[i] / c[i - 1] - 1) * 1e4 for i in range(max(1, len(c) - 30), len(c)) if c[i - 1] > 0]
    mean = sum(rets) / len(rets) if rets else 0.0
    vol = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 if rets else 0.0
    return {"ret_5m_bps": ret(5), "ret_15m_bps": ret(15), "ret_60m_bps": ret(60), "vol_1m_bps": round(vol, 1)}


SYSTEM = """Voce e um trader intradia cauteloso numa conta DEMO da Kalshi (dinheiro de teste), operando perpetuos \
de acoes, cripto, cambio, metais e indices. Seu objetivo e expectativa positiva DEPOIS dos custos, nao atividade: \
na duvida, nao faca nada (acoes vazias e uma resposta valida e frequentemente a melhor).

Regras:
- Voce so recebe numeros do proprio sistema. Nao ha noticias; nao invente fatos sobre empresas.
- 'imb_100'/'imb_25'/'imb_topo5' vao de -1 (so venda no livro) a +1 (so compra); sao fracos sozinhos e podem ser
  armadilha (ofertas colocadas e retiradas). Pesem junto: tendencia (retornos), volatilidade e spread.
- Entrar + sair custa as duas taxas da corretora mais o spread: veja 'custo_ida_volta_bps' de cada candidato (em
  acoes e cripto passa de 24 bps; em metais, indices e cambio e bem menor). Em 'alvo_pct' informe o ganho que voce
  espera de verdade; o sistema recusa alvo abaixo de 'ganho_minimo_pct' e ativo que quase nao oscila perto disso.
  Nao infle o alvo para passar na trava. Fechar cedo por uma oscilacao de poucos minutos faz a taxa comer o resultado.
- Toda abertura precisa de 'usd', 'lado' e um 'stop_pct' coerente com a volatilidade (nem colado, que o ruido
  varre; nem longe demais). Respeite os limites que vierem em 'limites': o sistema recusa o que passar deles.
- Voce pode fechar posicoes abertas quando a tese acabou, o stop esta perto de ser tocado sem razao, ou o risco mudou.
- Cada acao leva um 'motivo' curto e verificavel nos numeros recebidos.
Responda SEMPRE chamando a ferramenta 'decide'."""

TOOL = {
    "name": "decide",
    "description": "Registra a decisao deste ciclo: uma analise curta e a lista de acoes (pode ser vazia).",
    "input_schema": {
        "type": "object",
        "properties": {
            "analise": {"type": "string", "description": "2 a 4 frases: o que viu e por que agiu ou ficou parado."},
            "acoes": {"type": "array", "items": {"type": "object", "properties": {
                "acao": {"type": "string", "enum": ["abrir", "fechar"]},
                "ativo": {"type": "string", "description": "id do ativo, ex.: NVDA"},
                "lado": {"type": "string", "enum": ["comprado", "vendido"]},
                "usd": {"type": "number", "description": "valor da entrada em USD"},
                "stop_pct": {"type": "number", "description": "stop em % do preco de entrada"},
                "alvo_pct": {"type": "number", "description": "ganho esperado em % (obrigatorio para abrir)"},
                "motivo": {"type": "string"}}, "required": ["acao", "ativo", "motivo"]}},
        },
        "required": ["analise", "acoes"],
    },
}


def build_user(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))


# ---- chamada ao modelo ----------------------------------------------------------------------------------------------
class LLMError(RuntimeError):
    pass


def call_claude(system: str, user: str, *, model: str, key: str, max_tokens: int = 1500, timeout: float = 90.0,
                opener=urllib.request.urlopen) -> tuple[dict, dict]:
    """Chama a API de mensagens forcando a ferramenta ``decide``. Devolve (entrada da ferramenta, uso de tokens)."""
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": system, "tools": [TOOL],
                       "tool_choice": {"type": "tool", "name": "decide"},
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    last: Exception | None = None
    for attempt in range(2):
        try:
            with opener(req, timeout=timeout) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            last = LLMError(f"HTTP {e.code}: {msg}")
            if e.code not in (429, 500, 502, 503, 529) or attempt:
                raise last from None
            time.sleep(3)
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = LLMError(f"falha de rede/resposta: {e}")
            if attempt:
                raise last from None
            time.sleep(3)
    else:  # pragma: no cover - o loop sempre levanta ou da break
        raise last or LLMError("sem resposta")
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "decide" and isinstance(block.get("input"), dict):
            return block["input"], data.get("usage", {})
    raise LLMError("o modelo nao chamou a ferramenta decide")


CLAUDE_HOME = Path("/var/lib/quant/claude-home")  # HOME do usuario do servico: onde fica o login da CLI do Claude


def call_cli(system: str, user: str, *, model: str, binary: str = "claude", home: Path = CLAUDE_HOME,
             timeout: float = 120.0, run=subprocess.run) -> tuple[dict, dict]:
    """Mesma decisao, pela CLI do Claude (``claude -p``) com o login da conta, sem chave de API.

    Sem ferramentas (``--tools ""``), sem sessao gravada e so a saida estruturada pelo esquema de ``decide``: a CLI nao
    pode ler arquivo nem rodar comando; so devolve o JSON da decisao, que passa pelas mesmas travas do codigo."""
    cmd = [binary, "-p", "--model", model, "--output-format", "json", "--json-schema", json.dumps(TOOL["input_schema"]),
           "--system-prompt", system, "--tools", "", "--no-session-persistence", "--setting-sources", ""]
    env = {**os.environ, "HOME": str(home)}
    try:
        p = run(cmd, input=user, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise LLMError(f"falha ao chamar a CLI: {e}") from None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        raise LLMError(f"CLI sem JSON (codigo {p.returncode}): {(p.stderr or p.stdout)[:300]}") from None
    if not isinstance(data, dict) or data.get("is_error"):
        raise LLMError(f"CLI com erro: {str((data or {}).get('result', ''))[:300]}")
    out = data.get("structured_output")
    if not isinstance(out, dict):
        try:
            out = json.loads(data.get("result") or "")
        except ValueError:
            out = None
    if not isinstance(out, dict):
        raise LLMError("a CLI nao devolveu a decisao estruturada")
    u = data.get("usage") or {}
    return out, {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0)}


def cli_ready(env=os.environ.get) -> bool:
    """A CLI so conta como pronta com o login gravado na pasta do servico."""
    return (Path(env("QUANT_CLAUDE_HOME", str(CLAUDE_HOME))) / ".claude" / ".credentials.json").exists()


# ---- ciclo ----------------------------------------------------------------------------------------------------------
@dataclass
class Deps:
    """Tudo que o ciclo toca no mundo; nos testes cada um vira um falso."""
    snapshot: Callable[[list[str]], list[dict]]          # fotos do livro (flow.snapshot_many)
    candles: Callable[[str], dict | None]                 # features de velas de um ativo
    positions: Callable[[], dict[str, dict]]              # ativo -> {side, contracts, entry}
    llm: Callable[[str, str], tuple[dict, dict]]          # (system, user) -> (decide.input, usage)
    execute: Callable[[dict], dict]                       # acao validada -> resultado do manual.execute
    runner: Callable[[], tuple[bool, set[str]]]           # (ativo?, ativos do runner)
    pnl_today: Callable[[float], float]
    last_close: Callable[[], dict[str, float]]
    kill: Callable[[], bool]
    mode_ok: Callable[[], bool]
    record_flow: Callable[[list[dict], int], None] = lambda rows, ts: None
    now: Callable[[], float] = time.time


def run_cycle(cfg: dict, deps: Deps, book: dict) -> dict:
    """Um ciclo completo. Devolve o registro (vai para decisions.jsonl). ``book`` e atualizado no lugar."""
    now = deps.now()
    rec: dict = {"t": int(now), "model": cfg["model"], "acoes": [], "erro": None}
    universe = assets_mod.parse(cfg["universe"])
    rows = deps.snapshot(universe)
    deps.record_flow(rows, int(now))
    runner_active, runner_assets = deps.runner()
    pos_all = deps.positions()
    held = {a: p for a, p in pos_all.items() if not (runner_active and a in runner_assets)}
    ctx = Ctx(universe=set(universe), held=held, runner_assets=runner_assets, runner_active=runner_active,
              kill=deps.kill(), mode_ok=deps.mode_ok(), pnl_today=deps.pnl_today(now), last_close=deps.last_close(),
              now=now)
    rec.update(universo=len(universe), fotos=len(rows), posicoes=sorted(held), pnl_dia=round(ctx.pnl_today, 4))

    forced = []  # fechamentos por regra (tempo maximo), antes de perguntar ao modelo
    for a in held:
        opened = (book.get(a) or {}).get("opened_at")
        if opened and now - opened > cfg["max_hold_h"] * 3600:
            forced.append({"acao": "fechar", "ativo": a, "motivo": f"tempo maximo de {cfg['max_hold_h']:g} h"})

    by_asset = {r["asset"]: r for r in rows}
    cand = pick_candidates(rows, set(held), cfg["candidates"], cfg["max_usd"])
    rec["candidatos"] = cand
    with ThreadPoolExecutor(max_workers=8) as pool:
        feats = dict(zip(cand, pool.map(lambda a: _safe(deps.candles, a), cand), strict=True))
    for a in cand:
        if a in by_asset:
            vol = (feats.get(a) or {}).get("vol_1m_bps")
            ctx.costs[a] = {"cost_bps": round_trip_bps(a, by_asset[a]["spread_bps"]),
                            "move_bps": None if vol is None else vol * 60 ** 0.5}
    snap = {
        "agora_utc": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "limites": {"max_usd_por_entrada": cfg["max_usd"], "max_posicoes": cfg["max_positions"],
                    "stop_pct_entre": [cfg["stop_min"], cfg["stop_max"]], "so_comprado": cfg["long_only"],
                    "max_acoes_por_ciclo": cfg["max_actions"], "cooldown_min": cfg["cooldown_min"]},
        "conta": {"posicoes_abertas": len(held), "vagas": max(0, cfg["max_positions"] - len(held)),
                  "pnl_realizado_hoje_usd": round(ctx.pnl_today, 4), "perda_maxima_dia_usd": cfg["max_daily_loss"]},
        "posicoes": [{"ativo": a, "lado": "comprado" if p["side"] > 0 else "vendido",
                      "resultado_pct": round(p["side"] * ((by_asset[a]["mark"] / p["entry"]) - 1) * 100, 2)
                      if a in by_asset and p.get("entry") else None,
                      "aberta_ha_min": round((now - (book.get(a) or {}).get("opened_at", now)) / 60),
                      "motivo_da_abertura": (book.get(a) or {}).get("reason", "")} for a, p in held.items()],
        "candidatos": [{"ativo": a, "classe": assets_mod.CATALOG[a]["cls"], "nome": assets_mod.CATALOG[a]["title"],
                        "spread_bps": round(by_asset[a]["spread_bps"], 1), "imb_25": round(by_asset[a]["imb_25"], 3),
                        "imb_100": round(by_asset[a]["imb_100"], 3), "imb_topo5": round(by_asset[a]["imb_top5"], 3),
                        "livro_usd_1pct": round(min(by_asset[a]["bid_usd_100"], by_asset[a]["ask_usd_100"])),
                        "custo_ida_volta_bps": round(ctx.costs[a]["cost_bps"], 1),
                        "ganho_minimo_pct": round(cfg["edge_min"] * ctx.costs[a]["cost_bps"] / 100, 3),
                        **(feats.get(a) or {})} for a in cand if a in by_asset],
    }
    try:
        decision, usage = deps.llm(SYSTEM, build_user(snap))
    except Exception as e:  # noqa: BLE001 - qualquer falha do modelo = ciclo sem acao (os stops continuam na corretora)
        rec["erro"] = f"{type(e).__name__}: {str(e)[:300]}"
        decision, usage = {"analise": "", "acoes": []}, {}
    rec["analise"] = str(decision.get("analise", ""))[:800]
    rec["uso"] = {k: usage.get(k) for k in ("input_tokens", "output_tokens") if k in usage}
    ok, bad = validate(decision.get("acoes", []), ctx, cfg)
    # regras proprias (tempo maximo) valem sempre, mesmo que o modelo tambem peca o fechamento
    seen = {(a["acao"], a["ativo"]) for a in ok}
    ok = [f for f in forced if ("fechar", f["ativo"]) not in seen] + ok
    for b in bad:
        rec["acoes"].append({**b, "status": "recusada"})
    for a in ok:
        if a["acao"] == "fechar":
            a = {**a, "entry_fee": (book.get(a["ativo"]) or {}).get("fee")}
        res = deps.execute(a)
        item = {k: a.get(k) for k in ("acao", "ativo", "side", "usd", "stop_pct", "alvo_pct", "motivo", "ajustado")}
        item.update(status="executada" if res.get("ok") else "falhou", detalhe=str(res.get("msg", ""))[:200])
        if res.get("aviso"):
            item["aviso"] = str(res["aviso"])[:200]
        rec["acoes"].append(item)
        if res.get("ok") and a["acao"] == "abrir":
            book[a["ativo"]] = {"opened_at": now, "reason": a["motivo"], "side": a["side"], "usd": a["usd"],
                                "fee": res.get("fee")}
            if "SEM stop" in str(res.get("aviso", "")):  # nunca fica posicao do agente sem stop
                close = deps.execute({"acao": "fechar", "ativo": a["ativo"], "motivo": "sem stop protetor",
                                      "entry_fee": res.get("fee")})
                item["fechada_por_seguranca"] = bool(close.get("ok"))
                if close.get("ok"):
                    book.pop(a["ativo"], None)
        elif res.get("ok") and a["acao"] == "fechar":
            book.pop(a["ativo"], None)
    return rec


def _safe(fn, a):
    try:
        return fn(a)
    except Exception:  # noqa: BLE001 - sem velas de um candidato: ele segue so com os numeros do livro
        log.exception("sem velas de %s", a)
        return None


# ---- arquivos e cola com o mundo real -------------------------------------------------------------------------------
def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)


def read_state(directory: Path) -> dict:
    return _read_json(directory / "state.json", {})


def read_book(directory: Path) -> dict:
    return _read_json(directory / "book.json", {})


def append_decision(path: Path, rec: dict, keep: int = 2000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > keep * 1.5:
            path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_decisions(path: Path, n: int = 40) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in reversed(lines):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def trades_of_agent(trades_path: Path | None, now: float) -> tuple[float, dict[str, float]]:
    """(PnL realizado hoje UTC, ultimo fechamento por ativo) das trades cujo motivo comeca com 'ia'."""
    import csv

    day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    pnl, last = 0.0, {}
    if trades_path is None:
        return pnl, last
    try:
        with trades_path.open(newline="") as f:
            for r in csv.DictReader(f):
                if not str(r.get("motivo", "")).startswith("ia"):
                    continue
                asset = str(r.get("origem", "")).split(":")[-1]
                try:
                    t = datetime.strptime(r["ts"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                    if r["ts"].startswith(day):
                        pnl += float(r["pnl"])
                    last[asset] = max(last.get(asset, 0.0), t)
                except (ValueError, KeyError):
                    continue
    except OSError:
        pass
    return pnl, last


def real_deps(env=os.environ.get, directory: Path = AGENT_DIR) -> Deps:
    """Dependencias de verdade: Binance/Kalshi publicas, executor da Kalshi demo e o Claude."""
    from . import flow, manual
    from .live.config import build_kalshi
    from .live.feed import KalshiFeed

    key = env("ANTHROPIC_API_KEY", "")
    cfg = load_config(directory / "config.json")
    trades = Path(env("QUANT_TRADES_LOG")) if env("QUANT_TRADES_LOG") else None
    state_dir = Path(env("QUANT_STATE", "/var/lib/quant/live_state.json")).parent
    kill = Path(env("QUANT_KILL_FILE", "/var/lib/quant/KILL"))
    flow_dir = Path(env("QUANT_FLOW_DIR", str(flow.FLOW_DIR)))
    feeds: dict[str, KalshiFeed] = {}

    def candles(a: str):
        if a not in feeds:
            feeds[a] = KalshiFeed(assets_mod.ticker(a), "1m")
        return candle_features(feeds[a].closed_bars(75))

    def positions() -> dict[str, dict]:
        ex = build_kalshi("testnet", env, assets_mod.ticker("BTC"))
        out: dict[str, dict] = {}
        by_ticker = {r["ticker"]: r["id"] for r in assets_mod.CATALOG.values()}
        params = {"subaccount": ex.subaccount} if ex.subaccount is not None else None
        for p in ex._req("GET", "/margin/positions", params=params).get("positions", []):
            n = float(p.get("position") or 0)
            if n and p.get("market_ticker") in by_ticker:
                out[by_ticker[p["market_ticker"]]] = {"side": 1 if n > 0 else -1, "contracts": abs(n),
                                                      "entry": float(p.get("entry_price") or 0)}
        return out

    def execute(a: dict) -> dict:
        asset = a["ativo"]
        ex = build_kalshi("testnet", env, assets_mod.ticker(asset))
        if a["acao"] == "abrir":
            req = manual.validate({"action": "open", "side": a["side"], "asset": asset, "usd": a["usd"],
                                   "stop_pct": a["stop_pct"]})
        else:
            req = manual.validate({"action": "close", "asset": asset})
            req["entry_fee"] = a.get("entry_fee")
        state = state_dir / f"live_state.{asset}.json"

        def price() -> float:
            return float(ex._market()["price"]) / ex.unit
        return manual.execute(req, ex, price_fn=price, kill_file=kill, trades_path=trades,
                              save_basis=manual._save_basis_factory(state), label=f"kalshi/testnet:{asset}",
                              why=f"ia: {a.get('motivo', '')[:80]}")

    def runner():
        cfgv = _read_runtime(Path(env("QUANT_RUNTIME_ENV", "/var/lib/quant/runtime.env")))
        names = [x for x in cfgv.get("QUANT_ASSETS", "").split(",") if x in assets_mod.CATALOG]
        import subprocess
        out = subprocess.run(["systemctl", "is-active", "quant-live"], capture_output=True, text=True).stdout
        active = out.strip() == "active"
        return active, set(names)

    return Deps(
        snapshot=lambda names: flow.snapshot_many(names), candles=candles, positions=positions,
        llm=(lambda s, u: call_cli(s, u, model=cfg["model"], binary=env("QUANT_CLAUDE_BIN", "claude"),
                                    home=Path(env("QUANT_CLAUDE_HOME", str(CLAUDE_HOME)))))
        if env("QUANT_AGENT_BACKEND", "api") == "cli"
        else (lambda s, u: call_claude(s, u, model=cfg["model"], key=key)),
        execute=execute, runner=runner,
        pnl_today=lambda now: trades_of_agent(trades, now)[0],
        last_close=lambda: trades_of_agent(trades, time.time())[1],
        kill=lambda: kill.exists(), mode_ok=lambda: env("QUANT_MODE") == "testnet" and env("QUANT_VENUE") == "kalshi",
        record_flow=lambda rows, ts: flow.write_rows(rows, flow_dir, ts))


def _read_runtime(path: Path) -> dict[str, str]:
    try:
        return dict(ln.split("=", 1) for ln in path.read_text().splitlines() if "=" in ln and not ln.startswith("#"))
    except OSError:
        return {}


def run_once(directory: Path = AGENT_DIR, *, force: bool = False, deps: Deps | None = None, now=time.time,
             env=os.environ.get) -> dict:
    """Um disparo do timer: respeita ligado/desligado e o intervalo; grava decisao, estado e livro."""
    cfg = load_config(directory / "config.json")
    state = _read_json(directory / "state.json", {})
    t = now()
    if not cfg["enabled"] and not force:
        return {"pulou": "desligado"}
    if not force and t - float(state.get("last_run", 0)) < cfg["interval_min"] * 60 - 5:
        return {"pulou": "intervalo"}
    state["last_run"] = t
    cli = env("QUANT_AGENT_BACKEND", "api") == "cli"
    if deps is None and not (cli_ready(env) if cli else env("ANTHROPIC_API_KEY", "")):
        state["last_error"] = ("login da CLI do Claude nao encontrado (deploy/login-claude-cli.sh)" if cli
                               else "chave da IA nao configurada (/etc/quant/agent.env)")
        _write_json(directory / "state.json", state)
        return {"erro": state["last_error"]}
    deps = deps or real_deps(env, directory)
    book = _read_json(directory / "book.json", {})
    rec = run_cycle(cfg, deps, book)
    _write_json(directory / "book.json", book)
    append_decision(directory / "decisions.jsonl", rec)
    state.update(last_error=rec["erro"], ciclos=int(state.get("ciclos", 0)) + 1,
                 tokens=int(state.get("tokens", 0)) + sum(int(v or 0) for v in rec["uso"].values()))
    # perda do dia estourada: o agente se desliga sozinho (religar e decisao humana, no painel)
    if rec["pnl_dia"] <= -cfg["max_daily_loss"] and cfg["enabled"]:
        save_config(directory / "config.json", {"enabled": False})
        state["last_error"] = (f"desligado: perda do dia {rec['pnl_dia']:.2f} atingiu o limite "
                               f"{cfg['max_daily_loss']:.2f}")
    _write_json(directory / "state.json", state)
    return rec


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    directory = Path(os.environ.get("QUANT_AGENT_DIR", str(AGENT_DIR)))
    if args and args[0] == "run":
        res = run_once(directory, force="--force" in args)
        print(json.dumps(res, ensure_ascii=False)[:2000])
        return 1 if res.get("erro") else 0
    if args and args[0] == "status":
        out = {"config": load_config(directory / "config.json"), "state": _read_json(directory / "state.json", {}),
               "ultimas": read_decisions(directory / "decisions.jsonl", 5)}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print("uso: python -m quant.agent run [--force] | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
