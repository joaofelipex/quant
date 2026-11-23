"""Regressoes da revisao do operador ao vivo: falhas de rede, barras perdidas, stop na corretora, fills reais."""
import logging

import pandas as pd
import pytest
from test_live import BAR, FLAT, T0, Feed, PaperExecutor, make_df, sig_fn

from quant.live.executor import BinanceFuturesExecutor
from quant.live.risk import RiskLimits, RiskManager
from quant.live.runner import Runner

ENTRY_ROWS = FLAT + [(100, 101, 99, 100)]  # sinal na barra 4 -> entra a 100, stop 80 (atr 10 x 2)


class WindowFeed(Feed):
    """Feed controlavel: ``offset`` desloca as datas (simula janela que nao cobre o intervalo)."""

    def __init__(self, rows):
        self.rows, self.offset = list(rows), pd.Timedelta(0)

    def closed_bars(self, n):
        df = make_df(self.rows)
        df["datetime"] = df["datetime"] + self.offset
        return df


class FlakyExecutor(PaperExecutor):
    """Primeira(s) ordem(ns) falham por rede."""

    def __init__(self, fail_times=1):
        super().__init__(slippage=0.0, fee_rate=0.0)
        self.fail = fail_times

    def market_order(self, *a, **k):
        if self.fail > 0:
            self.fail -= 1
            raise ConnectionError("rede caiu")
        return super().market_order(*a, **k)


class StopExecutor(PaperExecutor):
    """Paper com suporte a stop protetor na 'corretora'."""

    def __init__(self):
        super().__init__(slippage=0.0, fee_rate=0.0)
        self.stops = []

    def place_stop(self, side, qty, stop_price):
        self.stops.append((side, qty, stop_price))
        return str(len(self.stops))

    def cancel_stops(self):
        self.stops.clear()

    def has_stop(self):
        return bool(self.stops)


def build(tmp_path, rows, sigs, ex, now=None):
    feed = WindowFeed(rows)
    risk = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1000.0))
    clock = [now or (T0 + 5 * BAR + pd.Timedelta(seconds=2))]
    r = Runner(feed, ex, risk, sig_fn(sigs), qty=1.0, stop_atr=2.0, state_path=tmp_path / "s.json",
               kill_file=tmp_path / "KILL", now_fn=lambda: clock[0])
    return r, feed, risk


# ---- 1. falha ao enviar ordem nao perde o sinal ---------------------------------------------------------------
def test_falha_ao_enviar_entrada_e_repetida_no_mesmo_sinal(tmp_path):
    ex = FlakyExecutor(fail_times=1)
    r, _, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    with pytest.raises(ConnectionError):
        r.step()
    assert r.last_bar is None  # a barra NAO foi dada como processada
    assert r.step() == "entrada"  # rede voltou: mesmo sinal, entrada feita
    assert ex.position().side == 1 and r.entry["price"] == 100


def test_falha_ao_fechar_no_stop_e_repetida(tmp_path):
    class FlakyClose(PaperExecutor):
        broken = False

        def close_position(self, price_hint):
            if self.broken:
                self.broken = False
                raise ConnectionError("rede caiu")
            return super().close_position(price_hint)

    ex = FlakyClose(slippage=0.0, fee_rate=0.0)
    r, feed, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    assert r.step() == "entrada"
    feed.rows.append((100, 100, 79, 85))  # toca o stop
    r.signals, ex.broken = sig_fn({}), True
    with pytest.raises(ConnectionError):
        r.step()
    assert ex.position() is not None
    assert r.step() == "stop" and ex.position() is None  # nao ficou "sem barra nova"


# ---- 2. stop conferido em todas as barras novas -----------------------------------------------------------------
def test_stop_tocado_em_barra_perdida_e_executado(tmp_path):
    ex = PaperExecutor(slippage=0.0, fee_rate=0.0)
    r, feed, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    assert r.step() == "entrada"
    # a consulta falhou por 2 barras: chegam juntas; a 1a toca o stop (minima 70), a ultima ja recuperou
    feed.rows += [(100, 100, 70, 75), (96, 102, 95, 101)]
    r.signals = sig_fn({})
    assert r.step() == "stop"
    assert ex.position() is None
    assert r.risk.state()["pnl"] == pytest.approx(-20.0)  # abriu acima do stop: sai no stop


def test_gap_alem_do_stop_sai_na_abertura_da_barra(tmp_path):
    ex = PaperExecutor(slippage=0.0, fee_rate=0.0)
    r, feed, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    r.step()
    feed.rows += [(70, 72, 68, 71)]  # abre 70, abaixo do stop 80
    r.signals = sig_fn({})
    assert r.step() == "stop"
    assert r.risk.state()["pnl"] == pytest.approx(-30.0)  # pior que o stop, como no backtest


def test_janela_do_feed_sem_cobertura_fecha_a_posicao_por_seguranca(tmp_path):
    ex = PaperExecutor(slippage=0.0, fee_rate=0.0)
    r, feed, risk = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    r.step()
    feed.offset = 50 * BAR  # as barras devolvidas comecam muito depois da ultima processada
    r.signals = sig_fn({})
    assert r.step() == "lacuna"
    assert ex.position() is None and risk.halted


# ---- 3. stop protetor na corretora ---------------------------------------------------------------------------------
def test_entrada_coloca_stop_na_corretora_e_saida_cancela(tmp_path):
    ex = StopExecutor()
    r, feed, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    assert r.step() == "entrada"
    assert ex.stops == [(-1, 1.0, 80.0)]  # venda (lado de saida), qty da posicao, preco do stop
    feed.rows.append((100, 101, 99, 100))
    r.signals = sig_fn({5: -1})
    assert r.step() == "saida_sinal"
    assert ex.stops == []  # nao sobra stop velho para a proxima posicao


def test_sem_stop_protetor_fecha_e_trava(tmp_path):
    class NoStop(StopExecutor):
        def place_stop(self, *a, **k):
            raise ConnectionError("rede caiu")

    ex = NoStop()
    r, _, risk = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    assert r.step() == "sem_protecao"
    assert ex.position() is None and risk.halted


def test_stop_da_corretora_disparou_registra_a_perda(tmp_path):
    ex = StopExecutor()
    r, feed, risk = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    r.step()
    ex._pos = None  # a corretora executou o stop enquanto o runner dormia
    feed.rows.append((100, 100, 79, 85))
    r.signals = sig_fn({})
    assert r.step() == "ok"
    assert risk.state()["pnl"] == pytest.approx(-20.0) and r.entry is None and r.stop is None
    assert ex.stops == []


def test_stop_sumiu_da_corretora_e_recolocado(tmp_path):
    ex = StopExecutor()
    r, feed, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    r.step()
    ex.stops.clear()
    feed.rows.append((100, 101, 99, 100))
    r.signals = sig_fn({})
    r.step()
    assert ex.stops == [(-1, 1.0, 80.0)]


def test_fill_executado_mas_confirmacao_perdida_adota_a_posicao(tmp_path):
    class LostAck(StopExecutor):
        def market_order(self, *a, **k):
            super().market_order(*a, **k)
            raise TimeoutError("sem resposta")

    ex = LostAck()
    r, _, _ = build(tmp_path, ENTRY_ROWS, {4: 1}, ex)
    with pytest.raises(TimeoutError):
        r.step()
    assert ex.position() is not None and ex.stops == []  # posicao sem protecao
    r.step()  # proximo ciclo: reconcilia, adota e protege; o mesmo sinal nao dobra a posicao
    assert ex.position().qty == 1.0 and ex.stops == [(-1, 1.0, 80.0)] and r.entry["price"] == 100


# ---- 4. fills reais da Binance (ccxt falso) -----------------------------------------------------------------------
class FakeCcxt:
    def __init__(self, created, fetched=None, trades=None, open_orders=()):
        self.created, self.fetched, self.trades, self.open_orders = created, fetched, trades, list(open_orders)

    def amount_to_precision(self, symbol, qty):
        return qty

    def create_order(self, *a, **k):
        return self.created

    def fetch_order(self, order_id, symbol):
        if isinstance(self.fetched, Exception):
            raise self.fetched
        return self.fetched

    def fetch_my_trades(self, symbol, params=None):
        return self.trades or []

    def fetch_open_orders(self, symbol):
        return self.open_orders


def binance(monkeypatch, fake):
    monkeypatch.setattr(BinanceFuturesExecutor, "SETTLE_DELAY_S", 0)
    ex = BinanceFuturesExecutor.__new__(BinanceFuturesExecutor)  # sem tocar a rede
    ex.symbol, ex.ex = "ETH/USDT:USDT", fake
    return ex


def test_fill_sem_preco_medio_na_resposta_consulta_a_ordem(monkeypatch):
    fake = FakeCcxt({"id": "1", "status": "open", "average": None},
                    fetched={"id": "1", "status": "closed", "average": 101.5, "filled": 2.0,
                             "fees": [{"currency": "USDT", "cost": 0.08}]})
    fill = binance(monkeypatch, fake).market_order(1, 2.0, 100.0)
    assert (fill.price, fill.qty, fill.fee) == (101.5, 2.0, 0.08)


def test_taxa_vem_dos_trades_quando_a_ordem_nao_traz(monkeypatch):
    fake = FakeCcxt({"id": "1", "status": "closed", "average": 100.0, "filled": 1.0},
                    trades=[{"fee": {"currency": "USDT", "cost": 0.05}}])
    assert binance(monkeypatch, fake).market_order(1, 1.0, 100.0).fee == pytest.approx(0.05)


def test_sem_preco_e_sem_taxa_usa_referencia_com_aviso_alto(monkeypatch, caplog):
    fake = FakeCcxt({"id": "1", "status": "open", "average": None}, fetched=ConnectionError("x"))
    with caplog.at_level(logging.WARNING, logger="quant.live"):
        fill = binance(monkeypatch, fake).market_order(1, 2.0, 100.0)
    assert fill.price == 100.0 and fill.fee == pytest.approx(100.0 * 2.0 * 0.0004)
    assert any("sem preco medio" in m for m in caplog.messages)


def test_taxa_em_bnb_nao_e_somada_como_usdt(monkeypatch):
    fake = FakeCcxt({"id": "1", "status": "closed", "average": 100.0, "filled": 1.0,
                     "fees": [{"currency": "BNB", "cost": 0.0001}]})
    assert binance(monkeypatch, fake).market_order(1, 1.0, 100.0).fee == pytest.approx(100.0 * 1.0 * 0.0004)


def test_has_stop_enxerga_ordem_reduce_only_com_gatilho(monkeypatch):
    com = FakeCcxt({}, open_orders=[{"type": "stop_market", "reduceOnly": True, "stopPrice": 80.0}])
    sem = FakeCcxt({}, open_orders=[{"type": "limit", "reduceOnly": False}])
    assert binance(monkeypatch, com).has_stop() is True
    assert binance(monkeypatch, sem).has_stop() is False
