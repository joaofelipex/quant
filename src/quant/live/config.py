"""Configuracao por variaveis de ambiente. Padrao SEGURO: paper. Mainnet exige confirmacao explicita."""
from __future__ import annotations

import logging
import os

from quant.strategies import trend_follow as tf

from .executor import BinanceFuturesExecutor, PaperExecutor
from .feed import CcxtFeed, PublicSpotFeed
from .risk import RiskLimits, RiskManager
from .runner import Runner


def build_feed(mode: str, symbol: str, timeframe: str, kind: str, choice: str = "auto"):
    """``auto``: o paper le o endpoint PUBLICO de spot (alcancavel de qualquer regiao, sem chave); testnet/live leem a
    exchange via ccxt (precos do mesmo ambiente em que as ordens vao). ``public``/``ccxt`` forcam a escolha."""
    if choice not in {"auto", "public", "ccxt"}:
        raise SystemExit(f"QUANT_FEED invalido: {choice!r} (auto | public | ccxt)")
    if choice == "public" or (choice == "auto" and mode == "paper"):
        return PublicSpotFeed(symbol, timeframe)
    return CcxtFeed(symbol, timeframe, testnet=(mode == "testnet"), testnet_kind=kind)


def build_runner() -> Runner:
    env = os.environ.get
    mode = env("QUANT_MODE", "paper")  # paper | testnet | live
    symbol, tfm = env("QUANT_SYMBOL", "ETH/USDT:USDT"), env("QUANT_TIMEFRAME", "5m")
    kind = env("QUANT_TESTNET_KIND", "testnet")  # testnet (sandbox legado) | demo (Demo Trading)

    if mode == "paper":
        executor = PaperExecutor()
    elif mode in ("testnet", "live"):
        if mode == "live" and env("QUANT_ALLOW_MAINNET") != "yes-i-know":
            raise SystemExit("modo live exige QUANT_ALLOW_MAINNET=yes-i-know (e uma estrategia aprovada pelo README)")
        executor = BinanceFuturesExecutor(symbol, env("BINANCE_API_KEY", ""), env("BINANCE_API_SECRET", ""),
                                          testnet=(mode == "testnet"), testnet_kind=kind)
    else:
        raise SystemExit(f"QUANT_MODE invalido: {mode}")

    qty = float(env("QUANT_QTY", "0.01"))
    risk = RiskManager(RiskLimits(max_qty=float(env("QUANT_MAX_QTY", str(qty))),
                                  max_daily_loss=float(env("QUANT_MAX_DAILY_LOSS", "20"))))

    def signals(bars):  # mesma estrategia do backtest; cripto opera 24h, entao a janela de sessao e o dia todo
        return tf.generate_signals(tf.add_indicators(bars), session_start="00:00", session_end="23:59")

    feed = build_feed(mode, symbol, tfm, kind, env("QUANT_FEED", "auto"))
    return Runner(feed, executor, risk, signals, qty=qty,
                  timeframe=tfm, stop_atr=float(env("QUANT_STOP_ATR", "2.0")),
                  state_path=env("QUANT_STATE", "live_state.json"), kill_file=env("QUANT_KILL_FILE", "KILL"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    build_runner().run()


if __name__ == "__main__":
    main()
