"""Executor dos perps da Kalshi (API `margin`, https://docs.kalshi.com/margin). NAO TESTADO contra a exchange.

Valide no ambiente DEMO (``KALSHI_ENV=demo``, padrao) antes de qualquer coisa. As chaves nunca vem do chat: o id da
chave fica em ``KALSHI_API_KEY_ID`` e a chave privada num ARQUIVO (``KALSHI_PRIVATE_KEY_PATH``, modo 600), ambos no
``.env`` da VM.

Convencoes da Kalshi que o executor traduz para o resto do repo (que fala em unidades do ativo, ex.: ETH):
* ordem e posicao sao em CONTRATOS; 1 contrato = ``contract_size * underlying_multiplier`` do ativo (ETH: 0,001);
* preco e em DOLARES POR CONTRATO (preco do ativo x contract_size);
* nao ha ordem a mercado: usa-se limite IOC agressivo, a partir do livro da propria Kalshi;
* stop protetor = *exit trigger* (stop-loss no mark) da posicao, nao uma ordem; ao disparar vira uma ordem IOC perto do
  preco, entao pode preencher parcialmente ou nada (o runner reconfere o stop a cada barra).
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from pathlib import Path

from .executor import Executor, InsufficientFunds
from .models import Fill, Position

log = logging.getLogger("quant.live")

HOSTS = {"demo": "https://external-api.demo.kalshi.co", "prod": "https://external-api.kalshi.com"}
API = "/trade-api/v2"


def load_private_key(path: str | Path):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    return load_pem_private_key(Path(path).read_bytes(), password=None)


def sign(private_key, timestamp: str, method: str, path: str) -> str:
    """Assinatura da Kalshi: RSA-PSS/SHA-256 (RSA) ou Ed25519, sobre ``timestamp + METODO + caminho sem query``."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    msg = f"{timestamp}{method}{path.split('?')[0]}".encode()
    if isinstance(private_key, Ed25519PrivateKey):
        sig = private_key.sign(msg)
    else:
        pss = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH)
        sig = private_key.sign(msg, pss, hashes.SHA256())
    return base64.b64encode(sig).decode()


class KalshiError(RuntimeError):
    def __init__(self, msg: str, code: str | None = None):
        super().__init__(msg)
        self.code = code  # codigo da API (ex.: stop_loss_already_breached), quando o corpo traz um


class StopRejected(KalshiError):
    """A Kalshi recusou o stop protetor. O runner trata qualquer excecao de place_stop fechando a posicao e travando."""


# codigos de rejeicao de exit trigger (docs.kalshi.com/margin) e o que cada um significa para o runner
STOP_REJECTIONS = {
    "stop_loss_past_liquidation": "stop alem do preco de liquidacao (posicao alavancada demais para esse stop)",
    "stop_loss_already_breached": "preco ja passou do stop (gap): o stop dispararia na hora",
    "take_profit_already_breached": "preco ja passou do take-profit",
    "close_order_blocks_exit_trigger": "ha ordem de fechamento aberta que bloqueia o gatilho",
}


def _error_code(text: str) -> str | None:
    try:
        err = json.loads(text).get("error")
    except (ValueError, AttributeError):
        return None
    if isinstance(err, dict):
        return err.get("code") or err.get("details")
    return None


class KalshiPerpsExecutor(Executor):
    MAX_BOOK_DEV = 0.03      # livro mais longe que isso do preco justo (mark) e ignorado: oferta perdida/stale
    SLIPPAGE = 0.01          # teto de preco do limite IOC em relacao ao melhor preco do livro (1%)
    SETTLE_TRIES = 6         # espera a posicao refletir o fill (a Kalshi demora um instante a atualizar /positions)
    SETTLE_DELAY_S = 0.5

    def __init__(self, ticker: str, key_id: str, private_key, *, env: str = "demo", margin_mode: str = "cross",
                 subaccount: int | None = None, session=None, rebase: bool | None = None):
        if env not in HOSTS:
            raise ValueError(f"KALSHI_ENV invalido: {env!r} (demo | prod)")
        if margin_mode not in ("cross", "isolated"):
            raise ValueError(f"KALSHI_MARGIN_MODE invalido: {margin_mode!r} (cross | isolated)")
        if session is None:
            import requests

            session = requests.Session()
        self.ticker, self.key_id, self.key, self.env, self.mode = ticker, key_id, private_key, env, margin_mode
        self.subaccount, self.http, self.base = subaccount, session, HOSTS[env]
        # no demo o preco do perp nao acompanha o do feed (ex.: ETH a ~1.7 mil no demo): converte pela base de preco
        self.rebase = (env == "demo") if rebase is None else rebase
        self.basis = 1.0  # preco Kalshi (por unidade do ativo) / preco do feed
        m = self._market()
        self.unit = float(m["contract_size"]) * float(m["underlying_multiplier"])  # unidades do ativo por contrato
        self.tick = float(m["tick_size"])
        self.whole = not m.get("fractional_trading_enabled", False)
        self.min_qty = float(m["minimum_quantity"])
        self.contract_price = float(m.get("price") or 0)  # 1 contrato agora; ordem minima = isto x min_qty
        self.market_version = int(m.get("market_version", 0))

    # ---- HTTP ---------------------------------------------------------------------------------------------------
    def _req(self, method: str, path: str, *, params: dict | None = None, body: dict | None = None, auth: bool = True):
        full = API + path
        headers = {"Content-Type": "application/json"}
        if auth:
            ts = str(int(time.time() * 1000))
            headers.update({"KALSHI-ACCESS-KEY": self.key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
                            "KALSHI-ACCESS-SIGNATURE": sign(self.key, ts, method, full)})
        r = self.http.request(method, self.base + full, params=params, json=body, headers=headers, timeout=15)
        if r.status_code >= 400:
            raise KalshiError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}", _error_code(r.text))
        return r.json() if r.content else {}

    def _market(self) -> dict:
        return self._req("GET", f"/margin/markets/{self.ticker}", auth=False)["market"]

    # ---- conversoes ---------------------------------------------------------------------------------------------
    def _to_feed(self, contract_price: float) -> float:
        return contract_price / self.unit / self.basis

    def _to_contract_price(self, feed_price: float) -> float:
        return feed_price * self.basis * self.unit

    def _round_price(self, p: float, up: bool) -> float:
        n = p / self.tick
        n = -(-n // 1) if up else (n // 1)  # teto / piso
        return round(n * self.tick, 6)

    def _contracts(self, qty: float) -> float:
        n = qty / self.unit
        n = round(n) if self.whole else round(n, 2)
        if n < self.min_qty:
            raise KalshiError(f"quantidade {qty} = {n} contratos, abaixo do minimo {self.min_qty} "
                              f"(1 contrato = {self.unit})")
        return float(n)

    # ---- Executor -----------------------------------------------------------------------------------------------
    def export_state(self) -> dict | None:
        return {"basis": self.basis}

    def import_state(self, state: dict) -> None:
        self.basis = float((state or {}).get("basis") or 1.0)

    def position(self) -> Position | None:
        params = {"ticker": self.ticker}
        if self.subaccount is not None:
            params["subaccount"] = self.subaccount
        for p in self._req("GET", "/margin/positions", params=params)["positions"]:
            if p.get("market_ticker") != self.ticker:
                continue
            n = float(p["position"])
            if n:
                return Position(1 if n > 0 else -1, abs(n) * self.unit, self._to_feed(float(p["entry_price"])))
        return None

    def market_order(self, side: int, qty: float, price_hint: float, reduce_only: bool = False) -> Fill:
        if side not in (-1, 1) or qty <= 0:
            raise ValueError("side deve ser +1/-1 e qty > 0")
        m = self._market()
        if m.get("status") != "active":
            raise KalshiError(f"mercado {self.ticker} nao esta ativo (status={m.get('status')})")
        bid, ask = m.get("bid"), m.get("ask")
        ref = float(ask if side == 1 else bid or 0) or float(m["price"])
        mark = float(m["price"])
        if mark > 0 and abs(ref / mark - 1) > self.MAX_BOOK_DEV:
            # a demo tem ofertas soltas longe do preco (um short fechou a 20.000 com o mercado em 2.762): nunca cruza
            # o livro ate la; limita em volta do preco justo e, sem liquidez ali, a ordem simplesmente nao enche
            log.warning("%s: livro (%.4f) a mais de %.0f%% do preco justo (%.4f); usando o preco justo como referencia",
                        self.ticker, ref, self.MAX_BOOK_DEV * 100, mark)
            ref = mark
        if self.rebase and not reduce_only and price_hint > 0:
            self.basis = (float(m["price"]) / self.unit) / price_hint
        # limite IOC cruzando o livro, com teto de 1% de slippage; compra arredonda para cima, venda para baixo
        limit = self._round_price(ref * (1 + self.SLIPPAGE * side), up=(side == 1))
        count = self._contracts(qty)
        body = {"ticker": self.ticker, "client_order_id": uuid.uuid4().hex, "side": "bid" if side == 1 else "ask",
                "count": f"{count:.2f}", "price": f"{limit:.4f}", "time_in_force": "immediate_or_cancel",
                "self_trade_prevention_type": "taker_at_cross", "market_version": self.market_version}
        before = self.position() if reduce_only else None
        if reduce_only:
            body["reduce_only"] = True
        if self.subaccount is not None:
            body["subaccount"] = self.subaccount
        try:
            res = self._req("POST", "/margin/orders", body=body)
        except KalshiError as e:
            if not reduce_only and "available_balance_too_low" in f"{e.code} {e}":
                raise InsufficientFunds(f"{self.ticker}: saldo/margem insuficiente na conta ({e.code})") from e
            raise
        filled = float(res.get("fill_count") or 0)
        if filled <= 0:
            raise KalshiError(f"ordem IOC sem fill (limite {limit}, livro bid={bid} ask={ask}); nada foi aberto")
        avg = float(res.get("average_fill_price") or ref)
        fee = float(res.get("average_fee_paid") or 0) * filled
        if filled < count:
            log.warning("fill parcial: %s de %s contratos", filled, count)
        self._await_position(None if before is None else max(before.qty - filled * self.unit, 0.0))
        return Fill(side, filled * self.unit, self._to_feed(avg), fee)

    def _await_position(self, expect_qty: float | None) -> None:
        """Espera /positions refletir o fill. Sem isso o runner ve 'sem posicao' logo apos abrir e apaga o estado.
        ``expect_qty``: None = ao abrir, espera aparecer uma posicao; numero = ao reduzir, espera ficar <= ele."""
        for i in range(self.SETTLE_TRIES):
            pos = self.position()
            if (pos is not None) if expect_qty is None else ((pos.qty if pos else 0.0) <= expect_qty + 1e-9):
                return
            if i < self.SETTLE_TRIES - 1:
                time.sleep(self.SETTLE_DELAY_S)
        log.warning("posicao na Kalshi nao refletiu o fill em %.1f s; o runner vai reconciliar no proximo passo",
                    self.SETTLE_TRIES * self.SETTLE_DELAY_S)

    def _trigger_path(self) -> str:
        return f"/margin/{self.mode}/positions/{self.ticker}/exit_trigger"

    def place_stop(self, side: int, qty: float, stop_price: float) -> str | None:
        p = self._round_price(self._to_contract_price(stop_price), up=(side == 1))
        body = {"stop_loss_price": f"{p:.4f}"}
        try:
            res = self._req("PUT", self._trigger_path(), body=body)
        except KalshiError as e:
            reason = next((v for k, v in STOP_REJECTIONS.items() if k in (e.code or "") or k in str(e)), None)
            if reason:
                raise StopRejected(f"stop recusado pela Kalshi: {reason} ({e})", e.code) from e
            raise
        return str(res.get("id") or "")

    def cancel_stops(self) -> None:
        if not self._triggers():
            return
        self._req("DELETE", self._trigger_path())

    def _triggers(self) -> list[dict]:
        live = self._req("GET", self._trigger_path()).get("exit_triggers", [])
        return [t for t in live if t.get("status") in ("active", "pending_on_entry")]

    def has_stop(self) -> bool | None:
        return any(t.get("stop_loss_price") for t in self._triggers())
