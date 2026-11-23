"""Paper trading da carteira tsmom_cripto: roda uma vez por dia logo apos 00:00 UTC. NAO envia ordens a corretora.

Mecanica identica a do estudo (``quant.strategies.tsmom``): no dia D, na abertura,
1. realiza o PnL do peso mantido desde a abertura de D-1 (retorno de abertura a abertura, menos o funding de D-1);
2. calcula o alvo com os fechamentos ate D-1, aplica a banda e "entra" na abertura de D, pagando custo sobre o giro.
Se o servico ficar dias parado, o proximo disparo reproduz os dias perdidos com os dados historicos (idempotente).

    QUANT_PORT_STATE=/var/lib/quant/portfolio_state.json QUANT_PORT_LOG=/var/lib/quant/portfolio_log.csv \\
        python -m quant.live.portfolio
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from quant.strategies import tsmom

from .notify import Notify, no_notify, telegram_notifier

log = logging.getLogger("quant.live")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]


def _ccxt_symbol(s: str, perp: bool = False) -> str:
    base = s[:-4]
    return f"{base}/USDT:USDT" if perp else f"{base}/USDT"


def fetch_daily(symbols: list[str], limit: int = 400) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Abertura e fechamento diarios (spot, UTC). A ultima linha e o dia em curso: so a ABERTURA dela vale."""
    import ccxt

    ex = ccxt.binance({"enableRateLimit": True})
    opens, closes = {}, {}
    for s in symbols:
        raw = ex.fetch_ohlcv(_ccxt_symbol(s), "1d", limit=limit)
        idx = pd.to_datetime([r[0] for r in raw], unit="ms").normalize()
        opens[s] = pd.Series([r[1] for r in raw], index=idx)
        closes[s] = pd.Series([r[4] for r in raw], index=idx)
    return pd.DataFrame(opens), pd.DataFrame(closes)


def fetch_funding(symbols: list[str], since: pd.Timestamp) -> pd.DataFrame:
    """Funding somado por dia UTC (positivo = long paga). Falha de rede nao derruba o paper: vira 0 e e logada."""
    import ccxt

    ex = ccxt.binanceusdm({"enableRateLimit": True})
    ms = int(since.tz_localize("UTC").timestamp() * 1000)
    out = {}
    for s in symbols:
        try:
            h = ex.fetch_funding_rate_history(_ccxt_symbol(s, perp=True), since=ms, limit=1000)
            f = pd.Series([x["fundingRate"] for x in h], index=pd.to_datetime([x["timestamp"] for x in h], unit="ms"))
            out[s] = f.groupby(f.index.normalize()).sum()
        except Exception:  # noqa: BLE001
            log.exception("funding indisponivel para %s; assumindo 0", s)
    return pd.DataFrame(out)


class PortfolioPaper:
    def __init__(self, symbols: list[str], state_path: str | Path, log_path: str | Path, *, lookbacks=(20, 60, 120),
                 vol_target: float = 0.20, band: float = 0.03, cost_bps: float = 7.0, notify: Notify = no_notify):
        self.symbols = symbols
        self.state_path, self.log_path = Path(state_path), Path(log_path)
        self.lookbacks, self.vol_target, self.band, self.cost_bps = lookbacks, vol_target, band, cost_bps
        self.notify = notify

    # ---- estado ----------------------------------------------------------------------------------------------
    def load(self, today: pd.Timestamp) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"last_date": str(today - pd.Timedelta(days=1))[:10], "equity": 1.0,
                "weights": {s: 0.0 for s in self.symbols}}

    def _save(self, st: dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st))
        tmp.replace(self.state_path)  # escrita atomica

    # ---- um dia ----------------------------------------------------------------------------------------------
    def step(self, st: dict, day: pd.Timestamp, opens: pd.DataFrame, closes: pd.DataFrame,
             funding: pd.DataFrame) -> dict:
        prev = day - pd.Timedelta(days=1)
        held = np.array([st["weights"][s] for s in self.symbols])
        o = opens[self.symbols]
        ret = (o.loc[day] / o.loc[prev] - 1).fillna(0.0).to_numpy()
        fund = (funding.reindex(columns=self.symbols).loc[prev].fillna(0.0).to_numpy()
                if prev in funding.index else np.zeros(len(self.symbols)))
        pnl = float(held @ ret)
        fund_pnl = -float(held @ fund)

        tgt = tsmom.target_weights(closes[self.symbols].loc[:prev], lookbacks=self.lookbacks,
                                   vol_target=self.vol_target).iloc[-1].to_numpy()
        new = tsmom.band_step(tgt, held, self.band)
        turnover = float(np.abs(new - held).sum())
        cost = -turnover * self.cost_bps / 1e4

        st["equity"] *= 1 + pnl + fund_pnl + cost
        st["weights"] = dict(zip(self.symbols, map(float, new), strict=True))
        st["last_date"] = str(day)[:10]
        row = {"date": st["last_date"], "equity": st["equity"], "pnl": pnl, "funding": fund_pnl, "cost": cost,
               "turnover": turnover, "gross": float(np.abs(new).sum()),
               **{f"w_{s}": w for s, w in st["weights"].items()}}
        self._append(row)
        if turnover > 0:
            ordens = ", ".join(f"{s[:-4]} {n - h:+.1%}" for s, n, h in zip(self.symbols, new, held, strict=True)
                               if abs(n - h) > 1e-9)
            self.notify(f"{st['last_date']} rebalanceamento (paper): {ordens} | equity {st['equity']:.4f}")
        return row

    def _append(self, row: dict) -> None:
        new = not self.log_path.exists()
        with self.log_path.open("a", encoding="utf-8") as f:
            if new:
                f.write(",".join(row) + "\n")
            f.write(",".join(str(v) for v in row.values()) + "\n")

    def run(self, opens: pd.DataFrame, closes: pd.DataFrame, funding: pd.DataFrame, today: pd.Timestamp) -> list[dict]:
        """Processa todos os dias pendentes ate ``today`` (inclusive). Idempotente."""
        today = today.normalize()
        st = self.load(today)
        rows = []
        day = pd.Timestamp(st["last_date"]) + pd.Timedelta(days=1)
        while day <= today:
            if day not in opens.index or day - pd.Timedelta(days=1) not in closes.index:
                log.warning("sem dados para %s; parando", day.date())
                break
            rows.append(self.step(st, day, opens, closes, funding))
            self._save(st)
            day += pd.Timedelta(days=1)
        return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    env = os.environ.get
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    notify = telegram_notifier(token, chat, "quant-paper") if token and chat else no_notify
    bot = PortfolioPaper(SYMBOLS, env("QUANT_PORT_STATE", "portfolio_state.json"),
                         env("QUANT_PORT_LOG", "portfolio_log.csv"), notify=notify)
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    st = bot.load(today)
    opens, closes = fetch_daily(SYMBOLS)
    funding = fetch_funding(SYMBOLS, pd.Timestamp(st["last_date"]) - pd.Timedelta(days=1))
    rows = bot.run(opens, closes, funding, today)
    st = bot.load(today)
    log.info("dias processados: %d | ultimo: %s | equity: %.4f | pesos: %s", len(rows), st["last_date"], st["equity"],
             {s: round(w, 4) for s, w in st["weights"].items()})


if __name__ == "__main__":
    main()
