"""Mede a taxa de ordem limite (post_only) na Kalshi DEMO com o tamanho minimo. So mexe em ativos sem posicao e fora do
robo; ao final cancela o que sobrou e zera o que abriu (a mercado, reduce_only), aconteca o que acontecer."""
import os
import time
import uuid

from quant.live import assets as A
from quant.live.config import build_kalshi

assert os.environ.get("QUANT_MODE") == "testnet" and os.environ.get("QUANT_VENUE") == "kalshi"
runner = set(os.environ.get("QUANT_ASSETS", "").split(","))
base = build_kalshi("testnet", os.environ.get, A.ticker("BTC"))
assert base.env == "demo"
ocupados = {p["market_ticker"] for p in base._req("GET", "/margin/positions")["positions"] if float(p["position"])}

escolhidos = []
for a in ("HYPE", "KSHIB", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL", "META", "AMD", "INTC", "GOLD", "SILVER"):
    if a not in A.CATALOG or a in runner or A.ticker(a) in ocupados:
        continue
    ex = build_kalshi("testnet", os.environ.get, A.ticker(a))
    m = ex._market()
    bid, ask = float(m.get("bid") or 0), float(m.get("ask") or 0)
    aberto = m.get("status") == "active" and (m.get("schedule") or {}).get("is_open", True) is not False
    if not aberto or not bid or not ask or (ask / bid - 1) > 0.004:
        continue
    escolhidos.append((a, ex))
    if len(escolhidos) == 5:
        break
print("ativos do teste:", [a for a, _ in escolhidos])


def enviar(ex, side, count, price, **extra):
    body = {"ticker": ex.ticker, "client_order_id": uuid.uuid4().hex, "side": side, "count": f"{count:.2f}",
            "price": f"{price:.4f}", "self_trade_prevention_type": "taker_at_cross",
            "market_version": ex.market_version,
            **extra}
    return ex._req("POST", "/margin/orders", body=body)


def posicao(ex):
    for p in ex._req("GET", "/margin/positions", params={"ticker": ex.ticker})["positions"]:
        if p["market_ticker"] == ex.ticker:
            return float(p["position"])
    return 0.0


def cancelar(ex, oid):
    try:
        ex._req("DELETE", f"/margin/orders/{oid}")
    except Exception as e:  # noqa: BLE001 - ja executada ou ja cancelada
        if "404" not in str(e):
            print("  cancelar:", str(e)[:160])


inicio = int(time.time()) - 5
ordens, abertas = {}, {}
try:
    # 1) entrada: compra limite no melhor bid, so como maker
    for a, ex in escolhidos:
        m = ex._market()
        qtd = max(ex.min_qty, 1.0)
        try:
            r = enviar(ex, "bid", qtd, float(m["bid"]), time_in_force="good_till_canceled", post_only=True)
            ordens[r["order_id"]] = (a, ex, "entrada", time.time(), qtd)
            abertas[a] = r["order_id"]
            print(f"{a}: compra limite {qtd} @ {m['bid']} (ask {m['ask']}) executado na hora {r['fill_count']}")
        except Exception as e:  # noqa: BLE001
            print(a, "entrada recusada:", str(e)[:200])
    # prova do post_only: uma ordem que cruzaria o livro deve ser recusada/cancelada sem executar
    if escolhidos:
        a, ex = escolhidos[-1]
        try:
            r = enviar(ex, "bid", max(ex.min_qty, 1.0), float(ex._market()["ask"]), time_in_force="good_till_canceled",
                       post_only=True)
            ordens[r["order_id"]] = (a, ex, "cruzando", time.time(), 1.0)
            print("post_only cruzando:", {k: r.get(k) for k in ("fill_count", "remaining_count")})
            cancelar(ex, r["order_id"])
        except Exception as e:  # noqa: BLE001
            print("post_only cruzando: recusada:", str(e)[:200])

    # 2) espera ate 4 min; a cada posicao aberta, tenta sair com venda limite no melhor ask
    saidas = {}
    fim = time.time() + 240
    while time.time() < fim:
        time.sleep(10)
        for a, ex in escolhidos:
            q = posicao(ex)
            if q > 0 and a not in saidas:
                cancelar(ex, abertas.get(a, ""))
                m = ex._market()
                try:
                    r = enviar(ex, "ask", q, float(m["ask"]), time_in_force="good_till_canceled", post_only=True)
                    saidas[a] = r["order_id"]
                    ordens[r["order_id"]] = (a, ex, "saida", time.time(), q)
                    print(f"{a}: abriu {q}; venda limite @ {m['ask']}")
                except Exception as e:  # noqa: BLE001
                    print(a, "saida recusada:", str(e)[:200])
finally:
    for oid, (_, ex, *_resto) in ordens.items():
        cancelar(ex, oid)
    time.sleep(3)
    for a, ex in escolhidos:
        q = posicao(ex)
        if q:
            m = ex._market()
            lado = "ask" if q > 0 else "bid"
            ref = float(m["bid"] if q > 0 else m["ask"])
            try:
                r = enviar(ex, lado, abs(q), ref * (0.99 if q > 0 else 1.01), time_in_force="immediate_or_cancel",
                           reduce_only=True)
                ordens[r["order_id"]] = (a, ex, "zerar a mercado", time.time(), abs(q))
                print(f"{a}: zerado a mercado ({r['fill_count']})")
            except Exception as e:  # noqa: BLE001
                print(a, "NAO ZEROU:", str(e)[:200])
    time.sleep(3)
    fills = base._req("GET", "/margin/fills", params={"min_ts": inicio, "limit": 200}).get("fills", [])
    print("\nexecucoes do teste")
    for f in fills:
        if f["order_id"] in ordens:
            a, _, tipo, t0, _q = ordens[f["order_id"]]
            nocional = float(f["count"]) * float(f["price"])
            print(f"{a:6s} {tipo:16s} taker={f['is_taker']} qtd {f['count']} preco {f['price']} taxa {f['fees']} "
                  f"({float(f['fees']) / nocional * 1e4:.2f} bps) pnl {f.get('realized_pnl')}")
    print("posicoes restantes do teste:", {a: posicao(ex) for a, ex in escolhidos})
    abertas_api = base._req("GET", "/margin/orders", params={"status": "resting", "limit": 100}).get("orders", [])
    print("ordens paradas na conta:", [(o.get("ticker"), o.get("order_id") in ordens) for o in abertas_api])
