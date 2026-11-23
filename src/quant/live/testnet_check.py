"""Checagem de fumaca do executor da Binance NA TESTNET: o que o executor promete, a exchange cumpre?

    pip install -e ".[live]"
    BINANCE_API_KEY=... BINANCE_API_SECRET=... QUANT_TESTNET_KIND=testnet python -m quant.live.testnet_check

Abre e fecha UMA posicao minima (``QUANT_QTY``, padrao 0,01) e confere: fill, taxa, stop protetor, ``has_stop``,
cancelamento e saida reduce-only. Roteiro completo e criterios em ``docs/roteiro_testnet.md``.

Seguranca: este script SO fala com testnet/demo. Nao le ``QUANT_MODE``, nao tem opcao de mainnet e aborta se a URL
da API nao for de teste. Se ja houver posicao aberta na conta, nao toca em nada.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from .executor import BinanceFuturesExecutor, Executor

TEST_URL_MARKERS = ("testnet", "demo-fapi")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def assert_test_environment(ccxt_exchange) -> None:
    """Aborta se a URL privada da API nao for de testnet/demo. Ultima barreira contra tocar a mainnet."""
    url = str(ccxt_exchange.urls.get("api", {}).get("fapiPrivate", ""))
    if not any(m in url for m in TEST_URL_MARKERS):
        raise SystemExit(f"RECUSADO: a API configurada nao e de testnet/demo ({url or 'url vazia'}).")


def run_checks(ex: Executor, price_fn: Callable[[], float], qty: float, stop_pct: float = 0.03,
               emit: Callable[[Check], None] = lambda c: None) -> list[Check]:
    out: list[Check] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        c = Check(name, bool(ok), detail)
        out.append(c)
        emit(c)

    pos = ex.position()
    add("conta sem posicao aberta", pos is None, str(pos) if pos else "")
    if pos is not None:
        return out  # nao toca em posicao que nao e nossa
    px = float(price_fn())
    add("preco de referencia (ticker)", px > 0, f"{px:.4f}")

    try:
        fill = ex.market_order(1, qty, px)
        add("ordem a mercado preenche", fill.qty > 0, f"qty={fill.qty} @ {fill.price:.4f}")
        add("preco do fill a menos de 1% do ticker", abs(fill.price / px - 1) < 0.01, f"{fill.price / px - 1:+.3%}")
        add("taxa informada (> 0)", fill.fee > 0, f"{fill.fee:.6f}")
        pos = ex.position()
        add("posicao reconhecida pela corretora", pos is not None and pos.side == 1 and abs(pos.qty - fill.qty) < 1e-9,
            str(pos))

        stop_price = fill.price * (1 - stop_pct)
        sid = ex.place_stop(-1, fill.qty, stop_price)
        add("stop protetor aceito (devolve id)", sid is not None, f"id={sid} @ {stop_price:.4f}")
        add("has_stop() enxerga o stop", ex.has_stop() is True)
        ex.cancel_stops()
        add("cancel_stops() remove o stop", ex.has_stop() is False)

        ex.place_stop(-1, fill.qty, stop_price)  # saida deve funcionar COM stop pendente e nao deixar sobra
        close = ex.close_position(px)
        add("saida reduce-only fecha a posicao", close is not None and ex.position() is None,
            f"@ {close.price:.4f}" if close else "")
        if close is not None:
            gross = (close.price - fill.price) * fill.qty
            add("round-trip informativo (custo de ida e volta)", True,
                f"bruto {gross:+.4f} | taxas {fill.fee + close.fee:.4f}")
    except Exception as e:  # noqa: BLE001 - qualquer erro da exchange e um resultado da checagem
        add("execucao sem excecao", False, f"{type(e).__name__}: {e}")
    finally:
        try:  # limpeza: nunca deixar posicao nem stop na conta de teste
            ex.cancel_stops()
            if ex.position() is not None:
                ex.close_position(px)
            add("conta limpa ao final (sem posicao e sem stop)", ex.position() is None and ex.has_stop() is False)
        except Exception as e:  # noqa: BLE001
            add("conta limpa ao final (sem posicao e sem stop)", False, f"{type(e).__name__}: {e}")
    return out


def main() -> int:
    env = os.environ.get
    key, secret = env("BINANCE_API_KEY", ""), env("BINANCE_API_SECRET", "")
    if not key or not secret:
        print("Defina BINANCE_API_KEY e BINANCE_API_SECRET (chaves de TESTNET/DEMO, sem permissao de saque).")
        return 2
    symbol, qty = env("QUANT_SYMBOL", "ETH/USDT:USDT"), float(env("QUANT_QTY", "0.01"))
    kind = env("QUANT_TESTNET_KIND", "testnet")

    ex = BinanceFuturesExecutor(symbol, key, secret, testnet=True, testnet_kind=kind)  # testnet fixo no codigo
    assert_test_environment(ex.ex)
    print(f"{symbol} | qty {qty} | ambiente: {kind} | {ex.ex.urls['api']['fapiPrivate']}")

    def show(c: Check) -> None:
        print(f"  [{'OK ' if c.ok else 'FALHA'}] {c.name}" + (f" - {c.detail}" if c.detail else ""))

    results = run_checks(ex, lambda: float(ex.ex.fetch_ticker(symbol)["last"]), qty, emit=show)
    bad = [c for c in results if not c.ok]
    resumo = f"\n{len(results) - len(bad)}/{len(results)} checagens ok"
    print(resumo + (" | FALHARAM: " + "; ".join(c.name for c in bad) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
