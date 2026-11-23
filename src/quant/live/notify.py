"""Alertas. Nunca derrubam o servidor: falha ao avisar vira so um log."""
from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable

log = logging.getLogger("quant.live")

Notify = Callable[[str], None]


def no_notify(msg: str) -> None:
    log.info("[alerta] %s", msg)


def telegram_notifier(token: str, chat_id: str, prefix: str = "quant") -> Notify:
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(msg: str) -> None:
        log.info("[alerta] %s", msg)
        try:
            body = json.dumps({"chat_id": chat_id, "text": f"[{prefix}] {msg}"}).encode()
            req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).close()
        except Exception:  # noqa: BLE001
            log.exception("falha ao enviar alerta no Telegram")

    return send
