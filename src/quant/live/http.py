"""HTTP minimo e robusto para dados publicos (sem ccxt, sem chave)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def get_json(url: str, tries: int = 3, timeout: float = 20.0):
    """GET JSON com novas tentativas para 429/5xx/rede. Bloqueio regional (451) e erro definitivo: nao repete."""
    req = urllib.request.Request(url, headers={"User-Agent": "quant-paper/1.0"})
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == tries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries:
                raise
        time.sleep(2.0 * attempt)
    raise RuntimeError("inalcancavel")  # pragma: no cover
