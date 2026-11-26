"""Observabilidade: posicoes a partir das execucoes, quem abriu, sombra, problemas e a rota do painel."""
import json

import pytest

from quant import control, observ
from quant.live import assets

NOW = 1_795_000_000.0
NVDA = assets.CATALOG["NVDA"]["ticker"]
GOLD = assets.CATALOG["GOLD"]["ticker"]


def iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fill(i, ticker, t, side, count, pnl=0.0, fee=0.1, source="user"):
    return {"fill_id": str(i), "ticker": ticker, "created_time": iso(t), "side": side, "count": str(count),
            "realized_pnl": str(pnl), "fees": str(fee), "order_source": source}


DECISOES = [
    {"t": NOW - 600, "erro": None, "acoes": [{"acao": "abrir", "ativo": "NVDA", "status": "executada"}]},
    {"t": NOW - 300, "sombra": True, "erro": None, "analise": "x",
     "acoes": [{"acao": "abrir", "ativo": "GOLD", "status": "sombra"},
               {"acao": "fechar", "ativo": "SILVER", "status": "sombra", "liquido_bps": -12.5},
               {"acao": "abrir", "ativo": "BTC", "status": "recusada", "why": "alvo de 0.1% nao cobre (min 1%)"}]},
]
FILLS = [fill(1, NVDA, NOW - 590, "bid", 2), fill(2, NVDA, NOW - 100, "ask", 2, pnl=1.0),
         fill(3, GOLD, NOW - 5000, "bid", 1, source="system")]


def snap(**kw):
    base = dict(fills=FILLS, balance={"subaccount_balances": [{"account_equity": "100.8", "available_balance": "5"}]},
                positions=[{"market_ticker": GOLD, "position": "1", "entry_price": "3.5", "unrealized_pnl": "0.1"}],
                funding=[{"funding_amount": "-0.05"}], stops={GOLD: True}, decisions=DECISOES,
                agent_cfg={"enabled": True, "shadow": True, "interval_min": 5}, local_pnl=0.8,
                services=[{"unit": "x", "nome": "painel", "estado": "active"}], runner=[], kill=False,
                equity=[[NOW, 100.8]], now=NOW)
    base.update(kw)
    return observ.snapshot(**base)


class TestPosicoes:
    def test_agrupa_ate_zerar_e_identifica_quem_abriu(self):
        trips = observ.round_trips(FILLS, observ.ai_opens(DECISOES))
        nvda = next(v for v in trips if v["asset"] == "NVDA")
        ouro = next(v for v in trips if v["asset"] == "GOLD")
        assert nvda["quem"] == "ia" and nvda["fim"] is not None and nvda["taxa"] == pytest.approx(0.2)
        assert ouro["quem"] == "robo" and ouro["fim"] is None and ouro["corretora"]

    def test_liquido_soma_taxas_funding_e_aberto_e_fecha_o_saldo_inicial(self):
        c = snap()["conta"]
        assert c["liquido"] == pytest.approx(1.0 - 0.3 - 0.05 + 0.1)
        assert c["inicial_implicito"] == pytest.approx(100.8 - 0.75)

    def test_por_origem(self):
        linhas = {g["nome"]: g for g in snap()["por_origem"]}
        assert linhas["ia"]["ganhos"] == 1 and linhas["ia"]["liquido"] == pytest.approx(0.8)
        assert linhas["robo"]["fechadas"] == 0


class TestIAeProblemas:
    def test_sombra_e_recusas(self):
        s = snap()
        assert s["sombra"]["abertas"] == 1 and s["sombra"]["fechadas"] == 1 and s["sombra"]["media_bps"] == -12.5
        assert s["ia"]["recusas"] == [{"motivo": "alvo de 0.1% nao cobre", "n": 1}]
        assert s["ia"]["ultimo_ciclo_s"] == 300

    def test_tudo_certo_nao_gera_problema(self):
        assert snap()["problemas"] == []

    def test_sem_stop_servico_parado_e_registro_divergente(self):
        s = snap(stops={GOLD: False}, local_pnl=5.0,
                 services=[{"unit": "x", "nome": "painel", "estado": "failed"}],
                 runner=[{"asset": "ADA", "halted": True, "reason": "fechamento parcial"}])
        textos = " | ".join(p["texto"] for p in s["problemas"])
        assert "SEM stop" in textos and "com falha" in textos and "ADA" in textos and "difere" in textos
        assert s["problemas"][0]["nivel"] == "bad" and s["problemas"][-1]["nivel"] == "warn"

    def test_stop_desconhecido_nao_vira_alarme(self):
        assert snap(stops={})["problemas"] == []

    def test_ia_sem_ciclo_recente(self):
        s = snap(now=NOW + 3600)
        assert any("sem ciclo" in p["texto"] for p in s["problemas"])


class TestArquivos:
    def test_baixa_so_o_que_falta(self, tmp_path):
        pedidos = []

        class Ex:
            def _req(self, method, path, params=None):
                pedidos.append(params)
                return {"fills": FILLS[:2] if len(pedidos) == 1 else FILLS, "cursor": ""}

        arq = tmp_path / "fills.jsonl"
        assert len(observ.sync_fills(Ex(), arq)) == 2
        assert len(observ.sync_fills(Ex(), arq)) == 3
        assert "min_ts" not in pedidos[0] and pedidos[1]["min_ts"] == int(NOW - 100) - 600
        assert len(arq.read_text().splitlines()) == 3

    def test_painel_le_o_retrato_com_a_idade(self, tmp_path):
        arq = tmp_path / "metrics.json"
        assert control.read_metrics(arq) == {"disponivel": False}
        arq.write_text(json.dumps(snap()))
        got = control.read_metrics(arq, now=NOW + 30)
        assert got["disponivel"] and got["idade_s"] == 30 and got["conta"]["patrimonio"] == 100.8
