"""Configuracao por variaveis de ambiente. Padrao SEGURO: paper. Mainnet exige confirmacao explicita."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from quant.strategies import trend_follow as tf

from . import assets as assets_mod
from .executor import BinanceFuturesExecutor, PaperExecutor
from .feed import CcxtFeed, KalshiFeed, PublicSpotFeed
from .kalshi import KalshiPerpsExecutor, load_private_key
from .multi import MultiRunner
from .polymarket import PolymarketPerpsExecutor, load_credentials
from .risk import RiskLimits, RiskManager
from .runner import Runner

log = logging.getLogger("quant.live")


def build_kalshi(mode: str, env=os.environ.get, ticker: str | None = None) -> KalshiPerpsExecutor:
    """testnet = ambiente DEMO da Kalshi; live = producao (exige a confirmacao explicita, checada pelo chamador)."""
    key_id, key_path = env("KALSHI_API_KEY_ID", ""), env("KALSHI_PRIVATE_KEY_PATH", "")
    if not key_id or not key_path:
        raise SystemExit("KALSHI_API_KEY_ID e KALSHI_PRIVATE_KEY_PATH sao obrigatorios com QUANT_VENUE=kalshi")
    sub = env("KALSHI_SUBACCOUNT")
    return KalshiPerpsExecutor(ticker or env("KALSHI_TICKER", "KXETHPERP1"), key_id, load_private_key(key_path),
                               env="demo" if mode == "testnet" else "prod",
                               margin_mode=env("KALSHI_MARGIN_MODE", "cross"),
                               subaccount=int(sub) if sub else None)


def build_polymarket(env=os.environ.get) -> PolymarketPerpsExecutor:
    """Polymarket Perps nao tem testnet: so existe live (com a confirmacao explicita, checada pelo chamador)."""
    path = env("POLYMARKET_CREDENTIALS_PATH", "")
    if not path:
        raise SystemExit("POLYMARKET_CREDENTIALS_PATH e obrigatorio com QUANT_VENUE=polymarket")
    return PolymarketPerpsExecutor(env("POLYMARKET_SYMBOL", "ETH-USD"), load_credentials(path))


def build_feed(mode: str, symbol: str, timeframe: str, kind: str, choice: str = "auto", venue: str = "binance"):
    """``auto``: o paper le o endpoint PUBLICO de spot (alcancavel de qualquer regiao, sem chave); testnet/live leem a
    exchange via ccxt (precos do mesmo ambiente em que as ordens vao). ``public``/``ccxt`` forcam a escolha."""
    if choice not in {"auto", "public", "ccxt"}:
        raise SystemExit(f"QUANT_FEED invalido: {choice!r} (auto | public | ccxt)")
    public_venue = mode == "paper" or venue in ("kalshi", "polymarket")  # barras publicas da Binance, sem chave
    if choice == "public" or (choice == "auto" and public_venue):
        return PublicSpotFeed(symbol, timeframe)
    return CcxtFeed(symbol, timeframe, testnet=(mode == "testnet"), testnet_kind=kind)


def make_signals(env=os.environ.get):
    """Estrategia de tendencia (a do backtest). Canal Donchian e filtro de regime ER vem do ambiente. A pesquisa em 19
    cripto, 1 h, 2 anos fora da amostra (scripts/pesquisa_tendencia.py) so achou vantagem com ER >= 0,5, canal 55."""
    dc, er = int(env("QUANT_DONCHIAN", "20")), float(env("QUANT_ER", "0.5"))

    def signals(bars):  # cripto opera 24h, entao a janela de sessao e o dia todo
        return tf.generate_signals(tf.add_indicators(bars, donchian_period=dc), session_start="00:00",
                                   session_end="23:59", er_threshold=er)
    return signals


def build_runner() -> Runner:
    env = os.environ.get
    mode = env("QUANT_MODE", "paper")  # paper | testnet | live
    symbol, tfm = env("QUANT_SYMBOL", "ETH/USDT:USDT"), env("QUANT_TIMEFRAME", "5m")
    venue = env("QUANT_VENUE", "binance")  # binance | kalshi | polymarket
    kind = env("QUANT_TESTNET_KIND", "testnet")  # testnet (sandbox legado) | demo (Demo Trading)

    if mode == "paper":
        executor = PaperExecutor()
    elif mode in ("testnet", "live"):
        if mode == "live" and env("QUANT_ALLOW_MAINNET") != "yes-i-know":
            raise SystemExit("modo live exige QUANT_ALLOW_MAINNET=yes-i-know (e uma estrategia aprovada pelo README)")
        if venue == "polymarket" and mode != "live":
            raise SystemExit("Polymarket Perps nao tem testnet: valide em paper e depois so em live (com confirmacao)")
        if venue == "kalshi":
            executor = build_kalshi(mode, env)
        elif venue == "polymarket":
            executor = build_polymarket(env)
        elif venue == "binance":
            executor = BinanceFuturesExecutor(symbol, env("BINANCE_API_KEY", ""), env("BINANCE_API_SECRET", ""),
                                              testnet=(mode == "testnet"), testnet_kind=kind)
        else:
            raise SystemExit(f"QUANT_VENUE invalido: {venue!r} (binance | kalshi | polymarket)")
    else:
        raise SystemExit(f"QUANT_MODE invalido: {mode}")

    qty = float(env("QUANT_QTY", "0.01"))
    risk = RiskManager(RiskLimits(max_qty=float(env("QUANT_MAX_QTY", str(qty))),
                                  max_daily_loss=float(env("QUANT_MAX_DAILY_LOSS", "20"))))

    signals = make_signals(env)

    feed = build_feed(mode, symbol, tfm, kind, env("QUANT_FEED", "auto"), venue)
    return Runner(feed, executor, risk, signals, qty=qty,
                  timeframe=tfm, stop_atr=float(env("QUANT_STOP_ATR", "2.0")),
                  long_only=env("QUANT_DIRECTION", "both") == "long",
                  state_path=env("QUANT_STATE", "live_state.json"), kill_file=env("QUANT_KILL_FILE", "KILL"),
                  trades_path=env("QUANT_TRADES_LOG") or None, label=f"{venue}/{mode}")


def flow_gate(asset: str, minimum: float, snap=None):
    """Filtro de entrada pelo livro de ofertas: so deixa entrar se o desequilibrio (-1..+1) apoiar o lado do sinal em
    pelo menos ``minimum``. Sem foto util do livro, NAO entra (na duvida, fica de fora)."""
    from .. import flow
    snap = snap or flow.snapshot_one

    def gate(side: int) -> bool:
        f = snap(asset)
        return f is not None and side * float(f["imb_100"]) >= minimum
    return gate


def build_multi(env=os.environ.get) -> MultiRunner:
    """Um runner por ativo de ``QUANT_ASSETS`` (so Kalshi). Tamanho por valor: ``QUANT_NOTIONAL`` (USD) por entrada."""
    mode, venue = env("QUANT_MODE", "paper"), env("QUANT_VENUE", "binance")
    if venue != "kalshi" or mode != "testnet":
        raise SystemExit("QUANT_ASSETS (varios ativos) so funciona com QUANT_VENUE=kalshi e QUANT_MODE=testnet (demo)")
    try:
        names = assets_mod.parse(env("QUANT_ASSETS", ""))
    except ValueError as e:
        raise SystemExit(str(e)) from e
    tfm, kind = env("QUANT_TIMEFRAME", "5m"), env("QUANT_TESTNET_KIND", "testnet")
    notional = float(env("QUANT_NOTIONAL", "25"))
    state_dir = Path(env("QUANT_STATE", "live_state.json")).parent
    kill, trades = env("QUANT_KILL_FILE", "KILL"), env("QUANT_TRADES_LOG") or None

    signals = make_signals(env)
    flow_min = float(env("QUANT_FLOW_MIN", "0"))  # 0 = sem filtro de fluxo

    def prepare(a: str) -> Runner | None:
        try:
            ex = build_kalshi(mode, env, assets_mod.ticker(a))
            if ex.contract_price * ex.min_qty > notional * 1.5:  # 1 contrato ja passaria muito do valor por entrada
                log.warning("%s fora: o menor contrato vale %.2f USD (> 1,5 x %.2f); aumente QUANT_NOTIONAL",
                            a, ex.contract_price * ex.min_qty, notional)
                return None
            if assets_mod.uses_binance(a):
                feed = build_feed(mode, assets_mod.symbol(a), tfm, kind, env("QUANT_FEED", "auto"), venue)
            else:
                feed = KalshiFeed(assets_mod.ticker(a), tfm, env="demo")
            loss = float(env("QUANT_MAX_DAILY_LOSS", "20"))
            risk = RiskManager(RiskLimits(max_qty=float("inf"), max_daily_loss=loss))
            return Runner(feed, ex, risk, signals, qty=0.0, notional=notional, timeframe=tfm,
                          stop_atr=float(env("QUANT_STOP_ATR", "2.0")),
                          long_only=env("QUANT_DIRECTION", "both") == "long",
                          state_path=state_dir / f"live_state.{a}.json",
                          kill_file=kill, trades_path=trades, label=f"{venue}/{mode}:{a}",
                          flow_gate=flow_gate(a, flow_min) if flow_min > 0 else None,
                          trail_atr=float(env("QUANT_TRAIL_ATR", "0")), vol_size=env("QUANT_VOL_SIZE", "0") == "1")
        except Exception:  # noqa: BLE001 - um mercado fora do ar nao pode impedir os outros de subirem
            log.exception("nao consegui preparar %s; seguindo sem ele", a)
            return None

    # cada ativo faz 2 chamadas de rede ao subir (mercado + feed): em paralelo, 145 sobem em segundos, nao em minutos
    with ThreadPoolExecutor(max_workers=min(12, len(names))) as pool:
        runners = {a: r for a, r in zip(names, pool.map(prepare, names), strict=True) if r is not None}
    if not runners:
        raise SystemExit("nenhum dos ativos de QUANT_ASSETS pode ser operado agora (veja o log acima)")
    total = env("QUANT_MAX_TOTAL_LOSS")
    return MultiRunner(runners, max_total_loss=float(total) if total else None)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    (build_multi() if os.environ.get("QUANT_ASSETS", "").strip() else build_runner()).run()


if __name__ == "__main__":
    main()
