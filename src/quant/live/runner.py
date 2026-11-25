"""Loop principal: a cada barra fechada -> stop -> sinal -> risco -> ordem. Estado em disco, kill-switch por arquivo.

Garantias (cada uma tem teste em ``tests/test_live_robustez.py``):

* Uma barra so e marcada como processada DEPOIS de agir sobre ela; se o envio de uma ordem falha, o passo e
  repetido em segundos (nao na proxima barra) e a entrada/saida nao se perde.
* O stop e conferido em TODAS as barras fechadas desde a ultima processada, nao so na ultima; se a janela do feed
  nao cobre o intervalo, a posicao e fechada por seguranca.
* Toda entrada e seguida de um stop protetor na corretora (quando o executor suporta); se ele nao puder ser
  colocado, a posicao e fechada e o robo trava. A corretora e a fonte de verdade para a posicao.
"""
from __future__ import annotations

import csv
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from .executor import Executor, InsufficientFunds
from .feed import TIMEFRAME_SECONDS, Feed
from .risk import RiskManager

log = logging.getLogger("quant.live")

# estrategia: barras canonicas -> DataFrame com colunas ``signal`` (+1/-1/0) e ``atr`` (como no backtest)
SignalFn = Callable[[pd.DataFrame], pd.DataFrame]

TRADE_FIELDS = ["ts", "origem", "side", "qty", "entrada", "saida", "pnl", "motivo"]
def _px(x: float) -> str:
    """Preco no CSV: 4 casas para precos normais; algarismos significativos para ativos baratos (0.0551)."""
    return f"{x:.4f}" if abs(x) >= 1 else f"{x:.8g}"


_TRADES_LOCK = threading.Lock()  # varios ativos (threads) acrescentam ao mesmo CSV
RETRY_DELAY_S = 5.0  # apos erro num passo, tenta de novo logo (a barra ainda nao foi marcada como processada)


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


class Runner:
    def __init__(self, feed: Feed, executor: Executor, risk: RiskManager, signals: SignalFn, *, qty: float,
                 timeframe: str = "5m", stop_atr: float = 2.0, warmup: int = 300,
                 state_path: str | Path = "live_state.json", kill_file: str | Path = "KILL",
                 now_fn: Callable[[], pd.Timestamp] = _utc_now, trades_path: str | Path | None = None,
                 label: str = "", notional: float | None = None, long_only: bool = False):
        self.feed, self.executor, self.risk, self.signals = feed, executor, risk, signals
        self.qty, self.stop_atr, self.warmup = qty, stop_atr, warmup
        self.long_only = long_only  # so ABRE comprado; o sinal de venda continua fechando uma compra aberta
        self.notional = notional  # se informado, cada entrada vale ~este valor (USD) e ``qty`` e ignorada
        self.bar_s = TIMEFRAME_SECONDS[timeframe]
        self.state_path, self.kill_file, self.now_fn = Path(state_path), Path(kill_file), now_fn
        self.trades_path = Path(trades_path) if trades_path else None
        self.label = label  # ex.: "kalshi/testnet"; vai em cada linha do historico de trades
        self.last_bar: pd.Timestamp | None = None
        self.stop: float | None = None  # preco do stop (software e, se houver, corretora)
        self.stop_dist: float | None = None  # distancia do stop, para recalcular a partir do preco real de entrada
        self.entry: dict | None = None  # entrada CONFIRMADA: side, qty, price
        self._restore()

    def _size(self, price: float) -> float:
        """Quantidade da proxima entrada: fixa (``qty``) ou ``notional`` / preco (mesmo valor em qualquer ativo)."""
        return self.notional / price if self.notional else self.qty

    # ---- estado -----------------------------------------------------------------------------------------------
    def _save(self) -> None:
        s = {"last_bar": str(self.last_bar) if self.last_bar is not None else None, "stop": self.stop,
             "stop_dist": self.stop_dist, "entry": self.entry, "risk": self.risk.state(),
             "executor": self.executor.export_state()}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s))
        tmp.replace(self.state_path)  # escrita atomica

    def _restore(self) -> None:
        if self.state_path.exists():
            s = json.loads(self.state_path.read_text())
            self.last_bar = pd.Timestamp(s["last_bar"]) if s.get("last_bar") else None
            self.stop, self.stop_dist, self.entry = s.get("stop"), s.get("stop_dist"), s.get("entry")
            self.risk.load(s.get("risk", {}))
            if s.get("executor") is not None:
                self.executor.import_state(s["executor"])  # paper: a posicao simulada sobrevive ao reinicio
        pos = self.executor.position()  # a corretora manda: reconcilia na partida
        if pos is not None and self.stop is None:
            log.error("posicao aberta sem stop conhecido (%s): travando entradas, feche manualmente", pos)
            self.risk.halt("posicao orfa na partida")
        if pos is None:
            self.stop = self.stop_dist = self.entry = None

    def _record_trade(self, ts: pd.Timestamp, side: int, qty: float, entry: float, exit_: float, pnl: float,
                      why: str) -> None:
        """Acrescenta o trade fechado ao historico CSV (nunca derruba o runner se o disco falhar)."""
        if self.trades_path is None:
            return
        try:
            with _TRADES_LOCK:
                new = not self.trades_path.exists()
                with self.trades_path.open("a", newline="") as f:
                    w = csv.writer(f)
                    if new:
                        w.writerow(TRADE_FIELDS)
                    w.writerow([str(ts), self.label, side, f"{qty:.6f}", _px(entry), _px(exit_), f"{pnl:.4f}",
                                why])
        except OSError:
            log.exception("nao consegui gravar o historico de trades")

    # ---- ordens -----------------------------------------------------------------------------------------------
    def _cancel_stops(self) -> None:
        try:
            self.executor.cancel_stops()
        except Exception:  # noqa: BLE001 - nao pode impedir o fechamento; stop reduce-only sem posicao e inofensivo
            log.exception("falha ao cancelar stops pendentes")

    def _close(self, price: float, ts: pd.Timestamp, why: str) -> None:
        pos = self.executor.position()
        fill = self.executor.close_position(price)
        self._cancel_stops()  # depois de fechar: um stop velho nao pode sobrar para a proxima posicao
        self.stop = self.stop_dist = self.entry = None
        if pos is None or fill is None:
            return
        pnl = (fill.price - pos.entry) * pos.side * pos.qty - fill.fee  # taxa de entrada nao rastreada: aproximacao
        self.risk.record_trade(pnl, ts)
        self._record_trade(ts, pos.side, pos.qty, pos.entry, fill.price, pnl, why)
        log.info("saida (%s) @ %.4f pnl=%.2f", why, fill.price, pnl)

    def _protect(self, side: int, qty: float, ts: pd.Timestamp) -> bool:
        """Coloca o stop protetor na corretora. Se nao der, fecha a posicao e trava: nunca ficar sem protecao."""
        try:
            self._cancel_stops()
            self.executor.place_stop(-side, qty, float(self.stop))
        except Exception:  # noqa: BLE001
            log.exception("nao consegui colocar o stop protetor; fechando a posicao por seguranca")
            self._close(float(self.stop), ts, "sem stop protetor")
            self.risk.halt("falha ao colocar stop protetor")
            return False
        return True

    def _reconcile(self, now: pd.Timestamp):
        """Alinha o estado local com a corretora no inicio de cada passo. Devolve a posicao real."""
        pos = self.executor.position()
        if pos is None:
            if self.entry is not None:  # fechada fora do runner (tipicamente o stop da corretora disparou)
                e = self.entry
                pnl = (float(self.stop) - e["price"]) * e["side"] * e["qty"]  # estimativa: saiu no stop
                self.risk.record_trade(pnl, now)
                self._record_trade(now, e["side"], e["qty"], e["price"], float(self.stop), pnl,
                                   "stop da corretora (estimado)")
                log.warning("posicao fechada fora do runner (stop da corretora?); pnl estimado %.2f", pnl)
                self._cancel_stops()
            self.stop = self.stop_dist = self.entry = None  # inclui entrada que nao chegou a preencher
        elif self.entry is None and self.stop_dist is not None:  # preencheu mas a confirmacao se perdeu: adota
            self.entry = {"side": pos.side, "qty": pos.qty, "price": pos.entry}
            self.stop = pos.entry - pos.side * self.stop_dist
            log.warning("adotando posicao preenchida sem confirmacao: %s stop=%.4f", pos, self.stop)
            self._protect(pos.side, pos.qty, now)
            pos = self.executor.position()
        elif pos is not None and self.stop is not None and self.executor.has_stop() is False:
            log.error("stop protetor sumiu da corretora; recolocando")
            self._protect(pos.side, pos.qty, now)
            pos = self.executor.position()
        return pos

    def _first_stop_hit(self, new: pd.DataFrame, side: int) -> float | None:
        """Preco de saida da PRIMEIRA barra nova que tocou o stop (gap: sai na abertura, como no backtest)."""
        for b in new.itertuples():
            if side == 1 and b.low <= self.stop:
                return min(float(b.open), self.stop)
            if side == -1 and b.high >= self.stop:
                return max(float(b.open), self.stop)
        return None

    # ---- um passo ---------------------------------------------------------------------------------------------
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
        bar_close = last["datetime"] + pd.Timedelta(seconds=self.bar_s)
        now = self.now_fn()
        result = "ok"

        pos = self._reconcile(now)
        if pos is not None and self.stop is not None:  # stop por software em todas as barras desde a ultima processada
            truncated = self.last_bar is not None and bars.iloc[0]["datetime"] > self.last_bar
            new = bars[bars["datetime"] > self.last_bar] if self.last_bar is not None else bars.iloc[[-1]]
            if truncated:  # a janela do feed nao cobre o intervalo: nao da para provar que o stop nao foi tocado
                log.error("lacuna de dados com posicao aberta; fechando por seguranca")
                self._close(float(last["close"]), now, "lacuna de dados")
                self.risk.halt("lacuna de dados com posicao aberta")
                pos, result = None, "lacuna"
            else:
                hit = self._first_stop_hit(new, pos.side)
                if hit is not None:
                    self._close(hit, now, "stop")
                    pos, result = None, "stop"

        row = self.signals(bars).iloc[-1]
        sig = int(row["signal"])
        if pos is not None and sig == -pos.side:
            self._close(float(last["close"]), now, "sinal oposto")
            pos, result = None, "saida_sinal"
        atr_ok = float(row["atr"]) > 0  # mercado parado (atr 0/NaN) daria stop colado na entrada
        entry_sig = 0 if (self.long_only and sig < 0) else sig
        if pos is None and entry_sig != 0 and result == "ok" and atr_ok:
            ok, why = self.risk.check_entry(self._size(float(last["close"])), now, bar_close)
            if ok:
                try:
                    protected = self._enter(entry_sig, float(last["close"]), float(row["atr"]), now)
                    result = "entrada" if protected else "sem_protecao"
                except InsufficientFunds as e:  # sem margem: pula esta barra (repetir a cada 5 s so martela a API)
                    log.warning("entrada pulada: %s", e)
                    self.stop = self.stop_dist = self.entry = None
                    result = "sem_margem"
            else:
                log.warning("entrada bloqueada: %s", why)
                result = "bloqueada"
        self.last_bar = last["datetime"]  # so agora: se algo acima levantou excecao, a barra sera refeita
        self._save()
        return result

    def _enter(self, sig: int, hint: float, atr: float, now: pd.Timestamp) -> bool:
        """Entra a mercado e protege. Devolve False se a posicao teve de ser fechada por falta de stop."""
        self.stop_dist = self.stop_atr * atr
        self.stop, self.entry = hint - sig * self.stop_dist, None  # provisorios; salvos antes de mandar a ordem
        self._save()
        fill = self.executor.market_order(sig, self._size(hint), hint)
        self.entry = {"side": sig, "qty": fill.qty, "price": fill.price}
        self.stop = fill.price - sig * self.stop_dist
        log.info("entrada %+d @ %.4f stop=%.4f", sig, fill.price, self.stop)
        return self._protect(sig, fill.qty, now)

    def run(self) -> None:
        log.info("runner iniciado; kill-switch: crie o arquivo %s", self.kill_file)
        while True:
            delay = None
            try:
                if self.step() == "kill":
                    log.warning("kill-switch acionado; encerrando")
                    return
            except Exception:  # noqa: BLE001 - o servidor nao pode morrer por um erro de rede
                log.exception("erro no passo; tentando de novo em %.0fs", RETRY_DELAY_S)
                delay = RETRY_DELAY_S
            time.sleep(delay or max(5.0, self.bar_s - (time.time() % self.bar_s) + 2))  # 2s apos o fechamento
