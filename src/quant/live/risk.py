"""Gerenciador de risco: a ultima palavra antes de qualquer ordem de ENTRADA. Saidas nunca sao bloqueadas."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RiskLimits:
    max_qty: float  # tamanho maximo por ordem
    max_daily_loss: float  # em moeda da conta; ex.: 50 => para ao perder 50 no dia (UTC)
    max_trades_per_day: int = 20
    max_data_age_s: float = 120.0  # barra fechada ha mais que isso => feed parado


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self.halted = False
        self.halt_reason = ""
        self.halt_daily = False  # trava por perda do DIA: some na virada do dia UTC (as outras exigem decisao humana)
        self._day = None
        self._pnl = 0.0
        self._trades = 0

    def _roll(self, ts: pd.Timestamp) -> None:
        if self._day != ts.date():
            self._day, self._pnl, self._trades = ts.date(), 0.0, 0
            if self.halted and self.halt_daily:  # dia novo, limite novo
                self.halted, self.halt_reason, self.halt_daily = False, "", False

    def pnl_today(self, ts: pd.Timestamp) -> float:
        """PnL do dia de ``ts``: o guardado so vale se for do mesmo dia (o resto ja virou)."""
        return self._pnl if self._day == ts.date() else 0.0

    def halt(self, reason: str, *, daily: bool = False) -> None:
        self.halted, self.halt_reason, self.halt_daily = True, reason, daily

    def record_trade(self, pnl: float, ts: pd.Timestamp) -> None:
        self._roll(ts)
        self._pnl += pnl
        self._trades += 1
        if self._pnl <= -self.limits.max_daily_loss:
            self.halt(f"perda diaria {self._pnl:.2f} atingiu o limite {self.limits.max_daily_loss:.2f}", daily=True)

    def check_entry(self, qty: float, now: pd.Timestamp, bar_close: pd.Timestamp):
        """Devolve (ok, motivo). ``bar_close`` = instante em que a ultima barra fechada terminou."""
        self._roll(now)
        if self.halted:
            return False, f"parado: {self.halt_reason}"
        if qty > self.limits.max_qty:
            return False, f"qty {qty} > max_qty {self.limits.max_qty}"
        if self._trades >= self.limits.max_trades_per_day:
            return False, "limite de trades no dia"
        if (now - bar_close).total_seconds() > self.limits.max_data_age_s:
            return False, "dado atrasado/feed parado"
        return True, ""

    def state(self) -> dict:
        return {"day": str(self._day), "pnl": self._pnl, "trades": self._trades,
                "halted": self.halted, "reason": self.halt_reason, "halt_daily": self.halt_daily}

    def load(self, s: dict) -> None:
        day = s.get("day")
        self._day = pd.Timestamp(day).date() if day not in (None, "None") else None
        self._pnl, self._trades = s.get("pnl", 0.0), s.get("trades", 0)
        self.halted, self.halt_reason = s.get("halted", False), s.get("reason", "")
        # estados antigos nao tinham o campo: trava por perda e do dia
        self.halt_daily = bool(s.get("halt_daily", self.halted and self.halt_reason.startswith("perda ")))
