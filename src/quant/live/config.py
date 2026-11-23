"""Configuracao por variaveis de ambiente. Padrao SEGURO: paper. Mainnet exige confirmacao explicita."""
from __future__ import annotations

import logging
import os

from quant.strategies import trend_follow as tf

from .executor import BinanceFuturesExecutor, PaperExecutor
from .feed import CcxtFeed
from .risk import RiskLimits, RiskManager
from .runner import Runner


def build_runner() -> Runner:
    env = os.environ.get
    mode = env("QUANT_MODE", "paper")  # paper | testnet | live
    symbol, tfm = env("QUANT_SYMBOL", "ETH/USDT:USDT"), env("QUANT_TIMEFRAME", "5m")

    if mode == "paper":
        executor = PaperExecutor()
    elif mode in ("testnet", "live"):
        if mode == "live" and env("QUANT_ALLOW_MAINNET") != "yes-i-know":
            raise SystemExit("modo live exige QUANT_ALLOW_MAINNET=yes-i-know (e uma estrategia aprovada pelo README)")
        executor = BinanceFuturesExecutor(symbol, env("BINANCE_API_KEY", ""), env("BINANCE_API_SECRET", ""),
                                          testnet=(mode == "testnet"))
    else:
        raise SystemExit(f"QUANT_MODE invalido: {mode}")

    qty = float(env("QUANT_QTY", "0.01"))
    risk = RiskManager(RiskLimits(max_qty=float(env("QUANT_MAX_QTY", str(qty))),
                                  max_daily_loss=float(env("QUANT_MAX_DAILY_LOSS", "20"))))

    def signals(bars):  # mesma estrategia do backtest; cripto opera 24h, entao a janela de sessao e o dia todo
        return tf.generate_signals(tf.add_indicators(bars), session_start="00:00", session_end="23:59")

    return Runner(CcxtFeed(symbol, tfm, testnet=(mode == "testnet")), executor, risk, signals, qty=qty,
                  timeframe=tfm, stop_atr=float(env("QUANT_STOP_ATR", "2.0")),
                  state_path=env("QUANT_STATE", "live_state.json"), kill_file=env("QUANT_KILL_FILE", "KILL"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    build_runner().run()


if __name__ == "__main__":
    main()
