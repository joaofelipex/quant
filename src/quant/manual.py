"""Boleta manual: abre, protege e fecha posicao na Kalshi DEMO a pedido do painel.

Roda como unit oneshot (``quant-order.service``): quem tem a chave e esta aqui, nunca o processo web. O painel so grava
um pedido JSON validado e dispara a unit; o resultado volta por arquivo. Recusa o que nao for ``kalshi`` + ``testnet``.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("quant.manual")

ACTIONS = ("status", "open", "close", "stop")
MAX_QTY = 0.05                  # teto por ordem manual no ativo unico (50 contratos de 0.001 ETH)
MAX_USD = 200.0                 # teto por ordem manual quando o ativo e escolhido (tamanho em dolares)
STOP_PCT_RANGE = (0.1, 20.0)    # stop em % do preco de entrada
TRADE_FIELDS = ["ts", "origem", "side", "qty", "entrada", "saida", "pnl", "motivo"]  # = runner.TRADE_FIELDS


class OrderError(ValueError):
    """Pedido recusado (mensagem em portugues, mostrada no painel)."""


def validate(req: object) -> dict:
    """Normaliza e valida o pedido vindo do painel. Falha com OrderError."""
    if not isinstance(req, dict):
        raise OrderError("pedido deve ser um objeto JSON")
    action = req.get("action")
    if action not in ACTIONS:
        raise OrderError(f"acao invalida: {action!r} ({' | '.join(ACTIONS)})")
    out: dict = {"id": str(req.get("id") or "")[:64], "action": action}
    if req.get("asset") not in (None, ""):
        from .live.assets import CRYPTO

        if req["asset"] not in CRYPTO:
            raise OrderError(f"ativo invalido: {req['asset']!r}")
        out["asset"] = req["asset"]
    if action == "open":
        if req.get("side") not in (1, -1) or isinstance(req.get("side"), bool):
            raise OrderError("side deve ser 1 (comprar) ou -1 (vender)")
        out["side"] = int(req["side"])
        if "asset" in out:
            out["usd"] = _num(req.get("usd"), "valor em USD", 0.0, MAX_USD)
        else:
            out["qty"] = _num(req.get("qty"), "quantidade", 0.0, MAX_QTY)
    if action in ("open", "stop"):
        pct = req.get("stop_pct")
        if action == "stop" and pct is None:
            raise OrderError("informe o stop (% do preco de entrada)")
        out["stop_pct"] = None if pct is None else _num(pct, "stop %", *STOP_PCT_RANGE)
    return out


def _num(v: object, name: str, lo: float, hi: float) -> float:
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise OrderError(f"{name} deve ser um numero") from None
    if isinstance(v, bool) or not (lo < x <= hi if lo == 0 else lo <= x <= hi) or x != x:
        raise OrderError(f"{name} deve estar entre {lo} e {hi}")
    return x


def spot_price(symbol: str) -> float:
    """Ultimo preco do feed publico (a base usada pelo executor para converter o preco do demo)."""
    import requests

    pair = symbol.split(":")[0].replace("/", "")
    r = requests.get("https://data-api.binance.vision/api/v3/ticker/price", params={"symbol": pair}, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])


def _position_view(ex, price: float | None) -> dict | None:
    pos = ex.position()
    if pos is None:
        return None
    try:
        stop = ex.has_stop()
    except Exception:  # noqa: BLE001 - so informativo
        stop = None
    upnl = None if price is None else round(pos.side * (price - pos.entry) * pos.qty, 4)
    return {"side": pos.side, "qty": pos.qty, "entry": pos.entry, "stop": stop, "price": price, "upnl": upnl}


def _record_trade(path: Path | None, side: int, qty: float, entry: float, exit_: float, pnl: float, why: str,
                  label: str) -> None:
    if path is None:
        return
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(TRADE_FIELDS)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([ts, label, side, f"{qty:.6f}", f"{entry:.4f}", f"{exit_:.4f}", f"{pnl:.4f}", why])


def execute(req: dict, ex, *, price_fn, kill_file: Path | None = None, trades_path: Path | None = None,
            save_basis=None, label: str = "kalshi/testnet") -> dict:
    """Executa um pedido ja validado. Devolve ``{ok, msg, aviso?, position}``; nunca levanta por regra de negocio."""
    from .live.kalshi import KalshiError, StopRejected

    action = req["action"]
    try:
        price = price_fn()
    except Exception:  # noqa: BLE001
        price = None
    if action == "status":
        return {"ok": True, "msg": "posicao atual", "position": _position_view(ex, price)}

    if action == "open":
        if kill_file is not None and kill_file.exists():
            return {"ok": False, "msg": "kill-switch ativo (arquivo KILL): remova-o antes de abrir posicao",
                    "position": _position_view(ex, price)}
        if ex.position() is not None:
            return {"ok": False, "msg": "ja existe posicao aberta: feche antes de abrir outra",
                    "position": _position_view(ex, price)}
        if price is None:
            return {"ok": False, "msg": "sem preco do feed publico agora; tente de novo", "position": None}
        try:
            fill = ex.market_order(req["side"], req["qty"] if "qty" in req else req["usd"] / price, price)
        except (KalshiError, ValueError) as e:
            return {"ok": False, "msg": f"ordem recusada: {e}", "position": _position_view(ex, price)}
        if save_basis:
            save_basis(ex.export_state())
        aviso = _protect(ex, fill.side, fill.qty, fill.price, req.get("stop_pct"), StopRejected, KalshiError)
        side = "COMPRA" if fill.side > 0 else "VENDA"
        res = {"ok": True, "msg": f"{side} executada: {fill.qty:g} @ {fill.price:.6g}",
               "position": _position_view(ex, price)}
        if aviso:
            res["aviso"] = aviso
        return res

    if action == "stop":
        pos = ex.position()
        if pos is None:
            return {"ok": False, "msg": "sem posicao aberta para proteger", "position": None}
        aviso = _protect(ex, pos.side, pos.qty, pos.entry, req["stop_pct"], StopRejected, KalshiError)
        res = {"ok": aviso is None, "msg": f"stop em {req['stop_pct']}% colocado" if aviso is None else aviso,
               "position": _position_view(ex, price)}
        return res

    # close
    pos = ex.position()
    if pos is None:
        return {"ok": True, "msg": "ja estava sem posicao", "position": None}
    try:
        fill = ex.close_position(price or pos.entry)
    except (KalshiError, ValueError) as e:
        return {"ok": False, "msg": f"nao consegui fechar: {e}", "position": _position_view(ex, price)}
    try:
        ex.cancel_stops()  # depois de fechar: um stop velho nao pode sobrar para a proxima posicao
    except Exception:  # noqa: BLE001
        log.exception("falha ao cancelar stops depois de fechar")
    pnl = 0.0
    if fill is not None:
        pnl = (fill.price - pos.entry) * pos.side * pos.qty - fill.fee
        try:
            _record_trade(trades_path, pos.side, pos.qty, pos.entry, fill.price, pnl, "manual", label)
        except OSError:
            log.exception("nao consegui gravar o historico de trades")
    return {"ok": True, "msg": f"posicao fechada, PnL {pnl:+.4f}", "position": _position_view(ex, price)}


def _protect(ex, side: int, qty: float, ref: float, pct: float | None, StopRejected, KalshiError) -> str | None:
    """Coloca o stop a ``pct`` % de ``ref``. Devolve um aviso se nao conseguiu (a posicao fica SEM stop)."""
    if pct is None:
        return "posicao aberta SEM stop (nenhum stop informado)"
    stop_price = ref * (1 - side * pct / 100)
    try:
        ex.cancel_stops()
        ex.place_stop(-side, qty, stop_price)
    except (StopRejected, KalshiError) as e:
        return f"posicao aberta SEM stop: {e}"
    return None


def _save_basis_factory(state_path: Path):
    def save(exec_state: dict | None) -> None:
        """Grava a base de preco no estado do runner, para ele reconciliar uma posicao aberta a mao."""
        try:
            st = json.loads(state_path.read_text()) if state_path.exists() else {}
            st["executor"] = {**(st.get("executor") or {}), **(exec_state or {})}
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(st))
            tmp.replace(state_path)
        except (OSError, ValueError):
            log.exception("nao consegui gravar a base de preco no estado")
    return save


def main(env=os.environ.get) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    req_path = Path(env("QUANT_ORDER_REQUEST", "/var/lib/quant/order-request.json"))
    res_path = Path(env("QUANT_ORDER_RESULT", "/var/lib/quant/order-result.json"))
    rid = ""
    try:
        raw = json.loads(req_path.read_text())
        rid = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        req = validate(raw)
        # trava dura: so demo da Kalshi. Producao/outras corretoras nunca passam por aqui.
        if env("QUANT_MODE", "paper") != "testnet" or env("QUANT_VENUE", "binance") != "kalshi":
            raise OrderError("boleta manual so funciona com QUANT_VENUE=kalshi e QUANT_MODE=testnet (demo)")
        from .live import assets
        from .live.config import build_kalshi

        asset = req.get("asset")
        ex = build_kalshi("testnet", env, assets.ticker(asset) if asset else None)
        state_path = Path(env("QUANT_STATE", "/var/lib/quant/live_state.json"))
        if asset:  # cada ativo tem o proprio estado (a base de preco do demo e por mercado)
            state_path = state_path.parent / f"live_state.{asset}.json"
        if state_path.exists():
            try:
                ex.import_state(json.loads(state_path.read_text()).get("executor") or {})
            except (OSError, ValueError):
                pass
        trades = env("QUANT_TRADES_LOG")
        symbol = assets.symbol(asset) if asset else env("QUANT_SYMBOL", "ETH/USDT:USDT")
        out = execute(req, ex, price_fn=lambda: spot_price(symbol), kill_file=Path(env("QUANT_KILL_FILE", "KILL")),
                      trades_path=Path(trades) if trades else None, save_basis=_save_basis_factory(state_path),
                      label=f"kalshi/testnet:{asset}" if asset else "kalshi/testnet")
    except OrderError as e:
        out = {"ok": False, "msg": str(e), "position": None}
    except Exception as e:  # noqa: BLE001 - o painel precisa de uma resposta, mesmo em erro inesperado
        log.exception("falha na boleta manual")
        out = {"ok": False, "msg": f"erro inesperado: {type(e).__name__}: {str(e)[:200]}", "position": None}
    out.update(id=rid, at=int(time.time()))
    tmp = res_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(res_path)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
