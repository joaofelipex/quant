"""Varios ativos num processo so: um ``Runner`` por ativo, cada um na sua hora, em paralelo, com risco total somado.

Cada ativo tem estado proprio (``live_state.<ATIVO>.json``), executor e perda diaria proprios. Cada runner so roda
quando a barra dele fecha (ou 5 s depois de um erro, so o dele). Com dezenas de ativos nao da para esperar um por um:
os que vencem juntos rodam numa pool de threads (o gargalo e a rede). O kill-switch (arquivo KILL) e unico e fecha todos
em ~1 s. Alem do limite por ativo, ``max_total_loss`` trava as ENTRADAS de todos quando a soma do PnL do dia chega nele
(saidas nunca sao bloqueadas).
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .runner import RETRY_DELAY_S, Runner

log = logging.getLogger("quant.live")


class MultiRunner:
    def __init__(self, runners: dict[str, Runner], *, max_total_loss: float | None = None, workers: int = 12,
                 sleep=time.sleep, clock=time.time):
        if not runners:
            raise ValueError("nenhum ativo para operar")
        self.runners, self.max_total_loss, self.sleep, self.clock = runners, max_total_loss, sleep, clock
        self.workers = max(1, min(workers, len(runners)))
        self.due = dict.fromkeys(runners, 0.0)   # quando cada ativo deve rodar de novo (epoch)
        self.last: dict[str, str] = {}           # ultimo resultado de cada ativo

    def total_pnl(self) -> float:
        """PnL do dia somado (so conta o dia atual: o que ficou de ontem ja virou)."""
        today = pd.Timestamp(self.clock(), unit="s")
        return sum(r.risk.pnl_today(today) for r in self.runners.values())

    def _check_total(self) -> None:
        if self.max_total_loss is not None and self.total_pnl() <= -self.max_total_loss:
            fresh = [r for r in self.runners.values() if not r.risk.halted]
            for r in fresh:
                r.risk.halt(f"perda total do dia {self.total_pnl():.2f} atingiu o limite {self.max_total_loss:.2f}",
                            daily=True)
            if fresh:
                log.error("limite de perda TOTAL atingido: entradas de todos os ativos travadas")

    def _step_one(self, name: str) -> str:
        try:
            return self.runners[name].step()
        except Exception:  # noqa: BLE001 - um ativo com problema de rede nao pode parar os demais
            log.exception("erro no passo de %s; tenta de novo em %.0f s", name, RETRY_DELAY_S)
            return "erro"

    def _next_due(self, name: str, result: str, now: float) -> float:
        if result == "erro":
            return now + RETRY_DELAY_S
        bar = self.runners[name].bar_s
        return now + bar - (now % bar) + 2.0  # 2 s depois do fechamento da barra (como o runner de um ativo so)

    def step_due(self) -> dict[str, str]:
        """Roda, em paralelo, os ativos cuja hora chegou. Devolve ``{ativo: resultado}`` so desses."""
        now = self.clock()
        if any(r.kill_file.exists() for r in self.runners.values()):
            self.due = dict.fromkeys(self.runners, 0.0)  # kill: todos agora, sem esperar a barra
        names = [n for n, t in self.due.items() if t <= now]
        if not names:
            return {}
        if self.workers == 1 or len(names) == 1:
            res = {n: self._step_one(n) for n in names}
        else:
            with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="ativo") as pool:
                res = dict(zip(names, pool.map(self._step_one, names), strict=True))
        end = self.clock()
        for n, r in res.items():
            self.due[n] = self._next_due(n, r, end)
        self.last.update(res)
        self._check_total()
        return res

    def run(self) -> None:
        log.info("runner multi-ativo iniciado (%d ativos: %s)", len(self.runners), ", ".join(self.runners))
        while True:
            self.step_due()
            if len(self.last) == len(self.runners) and all(v == "kill" for v in self.last.values()):
                log.warning("kill-switch acionado; encerrando")
                return
            wait = min(self.due.values()) - self.clock()
            self.sleep(min(1.0, max(0.05, wait)))  # espia o kill-switch a cada ~1 s
