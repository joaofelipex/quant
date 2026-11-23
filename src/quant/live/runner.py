"""Loop principal: a cada barra fechada -> stop -> sinal -> risco -> ordem. Estado em disco, kill-switch por arquivo."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from .executor import Executor
from .feed import TIMEFRAME_SECONDS, Feed
from .risk import RiskManager

log = logging.getLogger("quant.live")

# estrategia: barras canonicas -> DataFrame com colunas ``signal`` (+1/-1/0) e ``atr`` (como no backtest)
SignalFn = Callable[[pd.DataFrame], pd.DataFrame]


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


class Runner:
    def __init__(self, feed: Feed, executor: Executor, risk: RiskManager, signals: SignalFn, *, qty: float,
                 timeframe: str = "5m", stop_atr: float = 2.0, warmup: int = 300,
                 state_path: str | Path = "live_state.json", kill_file: str | Path = "KILL",
                 now_fn: Callable[[], pd.Timestamp] = _utc_now):
        self.feed, self.executor, self.risk, self.signals = feed, executor, risk, signals
        self.qty, self.stop_atr, self.warmup = qty, stop_atr, warmup
        self.bar_s = TIMEFRAME_SECONDS[timeframe]
        self.state_path, self.kill_file, self.now_fn = Path(state_path), Path(kill_file), now_fn
        self.last_bar: pd.Timestamp | None = None
        self.stop: float | None = None
        self._restore()

    # ---- estado -----------------------------------------------------------------------------------------------
    def _save(self) -> None:
        s = {"last_bar": str(self.last_bar) if self.last_bar is not None else None, "stop": self.stop,
             "risk": self.risk.state()}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s))
        tmp.replace(self.state_path)  # escrita atomica

    def _restore(self) -> None:
        if self.state_path.exists():
            s = json.loads(self.state_path.read_text())
            self.last_bar = pd.Timestamp(s["last_bar"]) if s.get("last_bar") else None
            self.stop = s.get("stop")
            self.risk.load(s.get("risk", {}))
        pos = self.executor.position()  # a corretora manda: reconcilia na partida
        if pos is not None and self.stop is None:
            log.error("posicao aberta sem stop conhecido (%s): travando entradas, feche manualmente", pos)
            self.risk.halt("posicao orfa na partida")
        if pos is None:
            self.stop = None

    # ---- um passo ---------------------------------------------------------------------------------------------
    def _close(self, price: float, ts: pd.Timestamp, why: str) -> None:
        pos = self.executor.position()
        fill = self.executor.close_position(price)
        if pos is None or fill is None:
            return
        pnl = (fill.price - pos.entry) * pos.side * pos.qty - fill.fee  # taxa de entrada nao rastreada: aproximacao
        self.risk.record_trade(pnl, ts)
        self.stop = None
        log.info("saida (%s) @ %.4f pnl=%.2f", why, fill.price, pnl)

    def step(self) -> str:
        if self.kill_file.exists():
            bars = self.feed.closed_bars(2)
            self._close(float(bars.iloc[-1]["close"]), self.now_fn(), "kill-switch")
            self.risk.halt("kill-switch")
            self._save()
            return "kill"

        bars = self.feed.closed_bars(self.warmup)
        last = bars.iloc[-1]
        if self.last_bar is not None and last["datetime"] <= self.last_bar:
            return "sem_barra_nova"
        self.last_bar = last["datetime"]
        bar_close = last["datetime"] + pd.Timedelta(seconds=self.bar_s)
        now = self.now_fn()
        result = "ok"

        pos = self.executor.position()
        if pos is not None and self.stop is not None:  # stop por software, checado na barra fechada
            hit = last["low"] <= self.stop if pos.side == 1 else last["high"] >= self.stop
            if hit:
                self._close(self.stop, now, "stop")
                pos, result = None, "stop"

        row = self.signals(bars).iloc[-1]
        sig = int(row["signal"])
        if pos is not None and sig == -pos.side:
            self._close(float(last["close"]), now, "sinal oposto")
            pos, result = None, "saida_sinal"
        if pos is None and sig != 0 and result == "ok":
            ok, why = self.risk.check_entry(self.qty, now, bar_close)
            if ok:
                fill = self.executor.market_order(sig, self.qty, float(last["close"]))
                self.stop = fill.price - sig * self.stop_atr * float(row["atr"])
                log.info("entrada %+d @ %.4f stop=%.4f", sig, fill.price, self.stop)
                result = "entrada"
            else:
                log.warning("entrada bloqueada: %s", why)
                result = "bloqueada"
        self._save()
        return result

    def run(self) -> None:
        log.info("runner iniciado; kill-switch: crie o arquivo %s", self.kill_file)
        while True:
            try:
                if self.step() == "kill":
                    log.warning("kill-switch acionado; encerrando")
                    return
            except Exception:  # noqa: BLE001 - o servidor nao pode morrer por um erro de rede
                log.exception("erro no passo; tentando de novo no proximo ciclo")
            time.sleep(max(5.0, self.bar_s - (time.time() % self.bar_s) + 2))  # acorda 2s apos o fechamento
