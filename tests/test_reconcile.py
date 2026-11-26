"""Conciliacao do historico local e mercado fechado."""
import pytest

from quant import agent, observ, reconcile
from quant.agent import Ctx, Deps, validate

T = 1_795_000_000.0


def ts(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def row(t, asset, pnl, motivo="stop", origem=None):
    return {"ts": ts(t), "origem": origem or f"kalshi/testnet:{asset}", "side": "1", "qty": "1", "entrada": "10",
            "saida": "9", "pnl": str(pnl), "motivo": motivo}


def trip(asset, fim, bruto, taxa=0.1, quem="ia"):
    return {"asset": asset, "fim": fim, "bruto": bruto, "taxa": taxa, "quem": quem}


class TestConciliacao:
    def test_cada_posicao_vira_uma_linha_com_o_resultado_da_corretora(self):
        rows = [row(T + 5, "ALU", -68.95), row(T + 1000, "NVDA", 0.5, "ia: x"), row(T + 1060, "NVDA", 0.5, "ia: x"),
                row(T + 9000, "ADA", -1.0), row(T, "x", 3.0, origem="paper")]
        trips = [trip("ALU", T, -51.6), trip("NVDA", T + 990, 0.4), trip("GOLD", T + 2000, 0.3),
                 trip("MCD", None, 0.0)]
        new = reconcile.rebuild(rows, trips)
        by = {(r["origem"], r["ts"]): r for r in new}
        assert float(by[("kalshi/testnet:ALU", ts(T + 5))]["pnl"]) == pytest.approx(-51.7)
        nvda = [r for r in new if r["origem"].endswith("NVDA")]
        assert len(nvda) == 1 and nvda[0]["motivo"] == "ia: x"  # a repetida some
        ouro = next(r for r in new if r["origem"].endswith("GOLD"))
        assert ouro["motivo"].startswith("ia") and float(ouro["pnl"]) == pytest.approx(0.2)
        ada = next(r for r in new if r["origem"].endswith("ADA"))
        assert ada["pnl"] == "0.0000" and ada["motivo"].endswith(reconcile.SEM_PAR)
        assert next(r for r in new if r["origem"] == "paper")["pnl"] == "3.0"
        assert reconcile.total(new) == pytest.approx(-51.7 + 0.3 + 0.2)

    def test_rodar_de_novo_nao_muda_nada(self):
        trips = [trip("NVDA", T, 0.4)]
        once = reconcile.rebuild([row(T, "NVDA", 9), row(T + 5000, "ADA", -1)], trips)
        assert reconcile.rebuild(once, trips) == once

    def test_registro_compara_so_posicoes_encerradas(self):
        fills = [{"fill_id": "1", "ticker": "A", "created_time": "2026-11-26T10:00:00Z", "side": "bid", "count": "1",
                  "realized_pnl": "0", "fees": "2"}]
        s = observ.snapshot(fills=fills, balance={}, positions=[], funding=[], stops={}, decisions=[], agent_cfg={},
                            local_pnl=0.0, services=[], runner=[], kill=False, equity=[], now=T)
        assert s["registro"]["diferenca"] == 0.0

    def test_mercado_fechado_nao_conta_como_ordem_falha(self):
        d = [{"t": T, "acoes": [{"status": "falhou", "detalhe": 'HTTP 409 {"code":"market_inactive"}'},
                                {"status": "falhou", "detalhe": "outra coisa"}]}]
        assert observ.agent_stats(d, T)["falhas_24h"] == 1


class TestMercadoFechado:
    def test_validador_recusa_abrir_e_fechar(self):
        c = Ctx(universe={"MCD"}, held={"MCD": {"side": 1}}, market_closed={"MCD"}, now=T)
        ok, bad = validate([{"acao": "fechar", "ativo": "MCD", "motivo": "x"}], c, agent.DEFAULTS)
        assert not ok and bad[0]["why"] == "mercado fechado agora"

    @pytest.mark.parametrize("resposta, envia", [(False, 0), (True, 1), (RuntimeError(), 1)])
    def test_fechamento_por_tempo_espera_o_mercado_abrir(self, resposta, envia):
        enviadas = []

        def aberto(a):
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        deps = Deps(snapshot=lambda n: [], candles=lambda a: None,
                    positions=lambda: {"MCD": {"side": 1, "contracts": 1, "entry": 5.0}},
                    llm=lambda s, u: ({"analise": "", "acoes": []}, {}),
                    execute=lambda a: enviadas.append(a) or {"ok": True, "msg": "ok"}, runner=lambda: (False, set()),
                    pnl_today=lambda t: 0.0, last_close=lambda: {}, kill=lambda: False, mode_ok=lambda: True,
                    now=lambda: T, is_open=aberto)
        agent.run_cycle({**agent.DEFAULTS, "universe": "MCD"}, deps, {"MCD": {"opened_at": T - 90000}})
        assert len(enviadas) == envia
