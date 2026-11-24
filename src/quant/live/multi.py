"""Varios ativos num processo so: um ``Runner`` por ativo, passos em sequencia, risco total somado.

Cada ativo tem estado proprio (``live_state.<ATIVO>.json``), executor proprio e perda diaria propria; o kill-switch
(arquivo KILL) e unico e fecha todos. Um erro num ativo nao para os outros. Alem do limite por ativo, ``max_total_loss``
trava as ENTRADAS de todos quando a soma do PnL do dia chega nele (saidas nunca sao bloqueadas).
"""
from __future__ import annotations

import logging
import time

from .runner import RETRY_DELAY_S, Runner

log = logging.getLogger("quant.live")


class MultiRunner:
    def __init__(self, runners: dict[str, Runner], *, max_total_loss: float | None = None, sleep=time.sleep,
                 clock=time.time):
        if not runners:
            raise ValueError("nenhum ativo para operar")
        self.runners, self.max_total_loss, self.sleep, self.clock = runners, max_total_loss, sleep, clock
        self.bar_s = min(r.bar_s for r in runners.values())

    def total_pnl(self) -> float:
        return sum(float(r.risk.state().get("pnl") or 0.0) for r in self.runners.values())

    def _check_total(self) -> None:
        if self.max_total_loss is not None and self.total_pnl() <= -self.max_total_loss:
            for r in self.runners.values():
                if not r.risk.halted:
                    r.risk.halt(f"perda total do dia {self.total_pnl():.2f} atingiu o limite {self.max_total_loss:.2f}")
            log.error("limite de perda TOTAL atingido: entradas de todos os ativos travadas")

    def step_all(self) -> dict[str, str]:
        """Um passo em cada ativo. Devolve ``{ativo: resultado}``; ``erro`` quando o passo levantou excecao."""
        out: dict[str, str] = {}
        for name, r in self.runners.items():
            try:
                out[name] = r.step()
            except Exception:  # noqa: BLE001 - um ativo com problema de rede nao pode parar os demais
                log.exception("erro no passo de %s; tenta de novo no proximo ciclo", name)
                out[name] = "erro"
        self._check_total()
        return out

    def run(self) -> None:
        log.info("runner multi-ativo iniciado (%d ativos: %s)", len(self.runners), ", ".join(self.runners))
        while True:
            res = self.step_all()
            if res and all(v == "kill" for v in res.values()):
                log.warning("kill-switch acionado; encerrando")
                return
            retry = any(v == "erro" for v in res.values())
            self.sleep(RETRY_DELAY_S if retry else max(5.0, self.bar_s - (self.clock() % self.bar_s) + 2))
