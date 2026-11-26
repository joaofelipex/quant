"""Agente de IA: travas de risco no CODIGO, configuracao, ciclo com falsos, chamada ao modelo e arquivos."""
import io
import json
import types
import urllib.error

import pandas as pd
import pytest

from quant import agent, manual
from quant.agent import Ctx, Deps, round_trip_bps, validate
from quant.live.models import Fill, Position

NOW = 1_795_000_000.0
CFG = {**agent.DEFAULTS, "enabled": True}


def ctx(**kw):
    nomes = {"BTC", "NVDA", "AAPL", "ETH", "SOL"}
    base = {"universe": nomes, "held": {}, "now": NOW,
            "costs": {a: {"cost_bps": 30.0, "move_bps": 100.0} for a in nomes}}
    base.update(kw)
    return Ctx(**base)


def abrir(ativo="NVDA", usd=10, stop=1.5, lado="comprado", motivo="teste"):
    return {"acao": "abrir", "ativo": ativo, "lado": lado, "usd": usd, "stop_pct": stop, "alvo_pct": 0.8,
            "motivo": motivo}


class TestCustos:
    def test_custo_soma_as_duas_taxas_e_o_spread(self):
        assert round_trip_bps("NVDA", 8.0) == pytest.approx(32.0)
        assert round_trip_bps("GOLD", 6.0) == pytest.approx(8.2)

    @pytest.mark.parametrize("alvo", [None, "x", 0, 0.59, float("nan")])
    def test_alvo_que_nao_paga_o_custo_e_recusado(self, alvo):
        ok, bad = validate([{**abrir(), "alvo_pct": alvo}], ctx(), CFG)
        assert not ok and "alvo" in bad[0]["why"]

    def test_ativo_parado_demais_e_recusado_mesmo_com_alvo_alto(self):
        c = ctx(costs={"NVDA": {"cost_bps": 30.0, "move_bps": 40.0}})
        assert "oscila" in validate([{**abrir(), "alvo_pct": 5}], c, CFG)[1][0]["why"]

    def test_sem_dados_de_custo_recusa_e_zero_desliga_a_trava(self):
        assert "sem dados" in validate([abrir()], ctx(costs={}), CFG)[1][0]["why"]
        assert validate([abrir()], ctx(costs={}), {**CFG, "edge_min": 0})[0]

    def test_taxa_de_entrada_entra_no_resultado(self, tmp_path):
        class Ex:
            pos = Position(1, 2.0, 100.0)

            def position(self):
                return self.pos

            def close_position(self, price):
                self.pos = None
                return Fill(-1, 2.0, 101.0, 0.30)

            def cancel_stops(self):
                pass

            def has_stop(self):
                return False

        trades = tmp_path / "t.csv"
        out = manual.execute({"action": "close", "entry_fee": 0.20}, Ex(), price_fn=lambda: 101.0, trades_path=trades)
        assert "+1.5000" in out["msg"]
        out = manual.execute({"action": "close"}, Ex(), price_fn=lambda: 101.0, trades_path=trades)
        assert "+1.4000" in out["msg"]  # sem a taxa guardada: estima igual a da saida


class TestSombra:
    CFG_S = {**CFG, "shadow": True, "edge_min": 0}

    def fake(self, decisao, mark=100.0, pos=None):
        enviadas = []
        rows = [{"asset": "NVDA", "spread_bps": 6.0, "mark": mark, "imb_25": 0.1, "imb_100": 0.1, "imb_top5": 0.1,
                 "bid_usd_100": 1e6, "ask_usd_100": 1e6}]
        deps = Deps(snapshot=lambda n: rows, candles=lambda a: {"vol_1m_bps": 20.0}, positions=lambda: pos or {},
                    llm=lambda s, u: ({"analise": "x", "acoes": decisao}, {}),
                    execute=lambda a: enviadas.append(a) or {"ok": True, "msg": "ok"},
                    runner=lambda: (False, set()), pnl_today=lambda t: 0.0, last_close=lambda: {},
                    kill=lambda: False, mode_ok=lambda: True, now=lambda: NOW)
        return deps, enviadas

    def test_abre_so_no_papel(self):
        deps, enviadas = self.fake([abrir()])
        book = {}
        rec = agent.run_cycle(self.CFG_S, deps, book)
        assert enviadas == [] and rec["sombra"] and rec["acoes"][0]["status"] == "sombra"
        assert book["NVDA"]["shadow"] and book["NVDA"]["entry"] == 100.0

    def test_fecha_no_papel_com_resultado_liquido_e_cooldown(self):
        book, closed = {}, {}
        agent.run_cycle(self.CFG_S, self.fake([abrir()])[0], book, closed)
        deps, enviadas = self.fake([{"acao": "fechar", "ativo": "NVDA", "motivo": "x"}], mark=101.0)
        rec = agent.run_cycle(self.CFG_S, deps, book, closed)
        assert enviadas == [] and book == {} and closed == {"NVDA": NOW}
        assert rec["acoes"][0]["liquido_bps"] == pytest.approx(100 - 30, abs=0.1)  # 2 x 12 + spread 6
        rec = agent.run_cycle(self.CFG_S, self.fake([abrir()])[0], book, closed)
        assert "cooldown" in rec["acoes"][0]["why"]

    def test_stop_simulado_sai_no_preco_do_stop(self):
        book = {}
        agent.run_cycle(self.CFG_S, self.fake([abrir(stop=1.0)])[0], book)
        deps, enviadas = self.fake([], mark=97.0)
        rec = agent.run_cycle(self.CFG_S, deps, book)
        assert enviadas == [] and book == {} and rec["acoes"][0]["liquido_bps"] == pytest.approx(-130, abs=0.1)

    def test_posicao_real_continua_podendo_ser_fechada(self):
        deps, enviadas = self.fake([{"acao": "fechar", "ativo": "NVDA", "motivo": "x"}],
                                   pos={"NVDA": {"side": 1, "contracts": 1, "entry": 99.0}})
        agent.run_cycle(self.CFG_S, deps, {})
        assert [a["acao"] for a in enviadas] == ["fechar"]

    def test_sair_do_modo_sombra_apaga_as_simuladas(self):
        book = {}
        agent.run_cycle(self.CFG_S, self.fake([abrir()])[0], book)
        agent.run_cycle({**CFG, "shadow": False}, self.fake([])[0], book)
        assert book == {}


class TestTravas:
    def test_abertura_valida_passa(self):
        ok, bad = validate([abrir()], ctx(), CFG)
        assert not bad and ok[0]["ativo"] == "NVDA" and ok[0]["side"] == 1 and ok[0]["usd"] == 10

    def test_valor_acima_do_maximo_e_cortado_no_maximo(self):
        ok, _ = validate([abrir(usd=500)], ctx(), CFG)
        assert ok[0]["usd"] == CFG["max_usd"] and ok[0]["ajustado"] is True

    @pytest.mark.parametrize("stop", [None, "x", 0, 0.2, 9, float("nan")])
    def test_stop_e_obrigatorio_e_dentro_da_faixa(self, stop):
        ok, bad = validate([abrir(stop=stop)], ctx(), CFG)
        assert not ok and bad

    @pytest.mark.parametrize("usd", [None, "x", 0, -5, float("nan")])
    def test_valor_invalido(self, usd):
        assert validate([abrir(usd=usd)], ctx(), CFG)[0] == []

    def test_so_comprado_por_padrao_e_vendido_quando_liberado(self):
        assert "long_only" in validate([abrir(lado="vendido")], ctx(), CFG)[1][0]["why"]
        ok, _ = validate([abrir(lado="vendido")], ctx(), {**CFG, "long_only": False})
        assert ok[0]["side"] == -1
        assert validate([abrir(lado="de lado")], ctx(), {**CFG, "long_only": False})[0] == []

    def test_ativo_fora_do_universo_ou_inventado(self):
        for a in ("XYZ", "", "KXBTCPERP1"):
            assert validate([abrir(ativo=a)], ctx(), CFG)[0] == []

    def test_nao_abre_o_que_o_runner_opera(self):
        c = ctx(runner_active=True, runner_assets={"NVDA"})
        assert "runner" in validate([abrir()], c, CFG)[1][0]["why"]
        assert validate([abrir()], ctx(runner_active=False, runner_assets={"NVDA"}), CFG)[0]  # runner parado: pode

    def test_limite_de_posicoes_conta_as_abertas_e_as_deste_ciclo(self):
        cfg = {**CFG, "max_positions": 2}
        c = ctx(held={"BTC": {"side": 1}})
        ok, bad = validate([abrir("NVDA"), abrir("AAPL")], c, cfg)
        assert [a["ativo"] for a in ok] == ["NVDA"] and "limite de 2 posicoes" in bad[0]["why"]

    def test_nao_abre_duas_vezes_o_mesmo_ativo(self):
        ok, bad = validate([abrir("NVDA"), abrir("NVDA")], ctx(), CFG)
        assert len(ok) == 1 and "ja existe" in bad[0]["why"]
        assert validate([abrir("NVDA")], ctx(held={"NVDA": {"side": 1}}), CFG)[0] == []

    def test_perda_do_dia_bloqueia_abertura_mas_nao_o_fechamento(self):
        c = ctx(pnl_today=-3.0, held={"NVDA": {"side": 1}})
        ok, bad = validate([abrir("AAPL"), {"acao": "fechar", "ativo": "NVDA", "motivo": "x"}], c, CFG)
        assert [a["acao"] for a in ok] == ["fechar"] and "perda do dia" in bad[0]["why"]

    def test_cooldown_depois_de_fechar(self):
        c = ctx(last_close={"NVDA": NOW - 5 * 60})
        assert "cooldown" in validate([abrir()], c, CFG)[1][0]["why"]
        assert validate([abrir()], ctx(last_close={"NVDA": NOW - 3600}), CFG)[0]

    def test_kill_e_modo_errado_recusam_tudo(self):
        for c in (ctx(kill=True), ctx(mode_ok=False)):
            ok, bad = validate([abrir(), {"acao": "fechar", "ativo": "BTC", "motivo": "x"}], c, CFG)
            assert not ok and len(bad) == 2

    def test_maximo_de_acoes_por_ciclo(self):
        acoes = [abrir(a) for a in ("NVDA", "AAPL", "ETH", "SOL")]
        ok, bad = validate(acoes, ctx(), {**CFG, "max_actions": 2, "max_positions": 10})
        assert len(ok) == 2 and "acima do maximo" in bad[0]["why"]

    def test_fechar_so_o_que_esta_aberto(self):
        assert validate([{"acao": "fechar", "ativo": "BTC", "motivo": "x"}], ctx(), CFG)[0] == []
        ok, _ = validate([{"acao": "fechar", "ativo": "btc", "motivo": "x"}], ctx(held={"BTC": {"side": 1}}), CFG)
        assert ok[0]["ativo"] == "BTC"

    @pytest.mark.parametrize("lixo", [None, "abrir tudo", {"acao": "abrir"}, [1, None, "x", {"acao": "vender"}]])
    def test_lixo_do_modelo_nunca_executa(self, lixo):
        ok, _ = validate(lixo, ctx(), CFG)
        assert ok == []


class TestConfig:
    def test_valida_faixas_e_tipos(self):
        assert agent.validate_config({"max_usd": 20, "long_only": False, "model": "claude-haiku-5-5"}) == {
            "max_usd": 20.0, "long_only": False, "model": "claude-haiku-5-5"}
        for bad in ({"max_usd": 1000}, {"max_usd": "x"}, {"enabled": "sim"}, {"model": "gpt"}, {"universe": "FOO"},
                    {"interval_min": 0}, {"api_key": "x"}, {"max_positions": True}):
            with pytest.raises(agent.ConfigError):
                agent.validate_config(bad)

    def test_universo_normaliza(self):
        assert agent.validate_config({"universe": "btc, nvda"})["universe"] == "BTC,NVDA"
        assert agent.validate_config({"universe": "TODOS"})["universe"] == "todos"

    def test_salvar_e_carregar_com_padroes_seguros(self, tmp_path):
        p = tmp_path / "config.json"
        assert agent.load_config(p)["enabled"] is False and agent.load_config(p)["long_only"] is True
        agent.save_config(p, {"enabled": True, "max_usd": 7})
        c = agent.load_config(p)
        assert c["enabled"] and c["max_usd"] == 7.0 and c["max_positions"] == agent.DEFAULTS["max_positions"]
        with pytest.raises(agent.ConfigError, match="stop_min"):
            agent.save_config(p, {"stop_min": 9, "stop_max": 2})

    def test_arquivo_corrompido_volta_aos_padroes(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("{nao e json")
        assert agent.load_config(p) == agent.DEFAULTS
        p.write_text(json.dumps({"max_usd": 99999, "enabled": True}))
        assert agent.load_config(p)["max_usd"] == agent.DEFAULTS["max_usd"]


def rows(*assets):
    out = []
    for i, a in enumerate(assets):
        out.append({"asset": a, "mark": 100.0, "bid": 99.9, "ask": 100.1, "spread_bps": 5.0 + i, "imb_25": 0.1 * i,
                    "imb_100": 0.9 - 0.2 * i, "imb_top5": 0.5, "bid_usd_100": 90_000.0, "ask_usd_100": 80_000.0})
    return out


class Fake:
    """Deps falsas que registram o que o ciclo fez."""

    def __init__(self, decision=None, positions=None, runner=(False, set()), exec_ok=True, aviso=None, llm_error=None,
                 pnl=0.0, kill=False, mode_ok=True):
        self.decision = decision or {"analise": "nada claro", "acoes": []}
        self.pos, self.runner_state, self.exec_ok, self.aviso = positions or {}, runner, exec_ok, aviso
        self.llm_error, self.pnl, self.killed, self.mode = llm_error, pnl, kill, mode_ok
        self.executed, self.prompts = [], []

    def deps(self, assets=("NVDA", "AAPL", "BTC")):
        def llm(system, user):
            self.prompts.append((system, user))
            if self.llm_error:
                raise self.llm_error
            return self.decision, {"input_tokens": 1200, "output_tokens": 150}

        def execute(a):
            self.executed.append(a)
            res = {"ok": self.exec_ok, "msg": "feito"}
            if self.aviso and a["acao"] == "abrir":
                res["aviso"] = self.aviso
            return res

        return Deps(snapshot=lambda names: rows(*[x for x in assets if x in names]),
                    candles=lambda a: {"ret_5m_bps": 3.0, "vol_1m_bps": 20.0},
                    positions=lambda: self.pos, llm=llm, execute=execute, runner=lambda: self.runner_state,
                    pnl_today=lambda t: self.pnl, last_close=lambda: {}, kill=lambda: self.killed,
                    mode_ok=lambda: self.mode, now=lambda: NOW)


class TestCiclo:
    def test_sem_acao_nao_executa_nada(self):
        f = Fake()
        rec = agent.run_cycle(CFG, f.deps(), {})
        assert f.executed == [] and rec["acoes"] == [] and rec["analise"] == "nada claro" and rec["erro"] is None
        assert rec["uso"] == {"input_tokens": 1200, "output_tokens": 150}

    def test_abre_aceita_e_registra_no_livro(self):
        f = Fake({"analise": "NVDA com fluxo comprador", "acoes": [abrir("NVDA", 12, 1.2, motivo="imb alto")]})
        book = {}
        rec = agent.run_cycle(CFG, f.deps(), book)
        assert f.executed[0]["acao"] == "abrir" and f.executed[0]["usd"] == 12
        assert rec["acoes"][0]["status"] == "executada"
        assert book["NVDA"]["reason"] == "imb alto" and book["NVDA"]["opened_at"] == NOW

    def test_o_que_passa_do_limite_nunca_chega_na_corretora(self):
        f = Fake({"analise": "x", "acoes": [abrir("NVDA", 12, 20), abrir("AAPL", 10, 1.0, lado="vendido")]})
        rec = agent.run_cycle(CFG, f.deps(), {})
        assert f.executed == [] and [a["status"] for a in rec["acoes"]] == ["recusada", "recusada"]

    def test_abertura_sem_stop_na_corretora_e_fechada_na_hora(self):
        f = Fake({"analise": "x", "acoes": [abrir("NVDA")]}, aviso="posicao aberta SEM stop: recusado")
        book = {}
        rec = agent.run_cycle(CFG, f.deps(), book)
        assert [a["acao"] for a in f.executed] == ["abrir", "fechar"] and "NVDA" not in book
        assert rec["acoes"][0]["fechada_por_seguranca"] is True

    def test_falha_do_modelo_vira_ciclo_sem_acao(self):
        f = Fake(llm_error=RuntimeError("HTTP 529 sobrecarregado"))
        rec = agent.run_cycle(CFG, f.deps(), {})
        assert f.executed == [] and "529" in rec["erro"]

    def test_corretora_recusou_nao_entra_no_livro(self):
        f = Fake({"analise": "x", "acoes": [abrir("NVDA")]}, exec_ok=False)
        book = {}
        rec = agent.run_cycle(CFG, f.deps(), book)
        assert rec["acoes"][0]["status"] == "falhou" and book == {}

    def test_tempo_maximo_fecha_mesmo_se_o_modelo_nao_pedir(self):
        f = Fake(positions={"NVDA": {"side": 1, "contracts": 3, "entry": 100.0}})
        book = {"NVDA": {"opened_at": NOW - 30 * 3600, "reason": "velha"}}
        rec = agent.run_cycle(CFG, f.deps(), book)
        assert [a["acao"] for a in f.executed] == ["fechar"] and "tempo maximo" in f.executed[0]["motivo"]
        assert "NVDA" not in book and rec["acoes"][0]["status"] == "executada"

    def test_ativos_do_runner_ficam_fora_das_posicoes_do_agente(self):
        f = Fake(positions={"NVDA": {"side": 1, "contracts": 1, "entry": 100.0}}, runner=(True, {"NVDA"}))
        rec = agent.run_cycle(CFG, f.deps(), {})
        assert rec["posicoes"] == []

    def test_prompt_so_tem_numeros_nossos_e_os_limites(self):
        f = Fake(positions={"BTC": {"side": 1, "contracts": 2, "entry": 98.0}})
        agent.run_cycle(CFG, f.deps(), {"BTC": {"opened_at": NOW - 600, "reason": "tendencia"}})
        system, user = f.prompts[0]
        snap = json.loads(user)
        assert snap["limites"]["max_usd_por_entrada"] == CFG["max_usd"]
        assert snap["conta"]["vagas"] == CFG["max_positions"] - 1
        assert snap["posicoes"][0]["ativo"] == "BTC"
        assert snap["posicoes"][0]["resultado_pct"] == pytest.approx(2.04, abs=0.01)
        assert {c["ativo"] for c in snap["candidatos"]} >= {"BTC", "NVDA"} and "decide" in system
        assert "ret_5m_bps" in snap["candidatos"][0]

    def test_candidatos_preferem_fluxo_forte_com_livro_e_spread_ok(self):
        r = rows("A1", "A2", "A3")
        r[0]["spread_bps"] = 80.0          # spread ruim
        r[1]["bid_usd_100"] = 10.0         # livro vazio
        assert agent.pick_candidates(r, set(), 5, 15.0) == ["A3"]
        assert agent.pick_candidates(r, {"A1"}, 5, 15.0)[0] == "A1"  # posicao aberta sempre entra


class TestFeatures:
    def test_retornos_e_volatilidade(self):
        close = [100.0 + i * 0.1 for i in range(80)]
        f = agent.candle_features(pd.DataFrame({"close": close}))
        assert f["ret_5m_bps"] == pytest.approx((close[-1] / close[-6] - 1) * 1e4, abs=0.1) and f["vol_1m_bps"] >= 0

    def test_poucas_barras(self):
        assert agent.candle_features(pd.DataFrame({"close": [1.0] * 5})) is None


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def resposta(inp):
    return FakeResp(json.dumps({"content": [{"type": "text", "text": "..."}, {"type": "tool_use", "name": "decide",
                                                                                "input": inp}],
                                "usage": {"input_tokens": 5, "output_tokens": 7}}).encode())


class TestClaude:
    def test_forca_a_ferramenta_e_devolve_a_decisao(self):
        visto = {}

        def opener(req, timeout):
            visto.update(headers=dict(req.header_items()), body=json.loads(req.data))
            return resposta({"analise": "ok", "acoes": []})

        out, uso = agent.call_claude("sys", "usr", model="claude-sonnet-5-5", key="sk-teste", opener=opener)
        assert out["analise"] == "ok" and uso["output_tokens"] == 7
        assert visto["body"]["tool_choice"] == {"type": "tool", "name": "decide"}
        assert visto["body"]["model"] == "claude-sonnet-5-5"
        assert visto["headers"]["X-api-key"] == "sk-teste" and visto["headers"]["Anthropic-version"] == "2023-06-01"

    def test_sem_a_ferramenta_e_erro(self):
        def opener(req, timeout):
            return FakeResp(json.dumps({"content": [{"type": "text", "text": "oi"}]}).encode())

        with pytest.raises(agent.LLMError, match="nao chamou"):
            agent.call_claude("s", "u", model="m", key="k", opener=opener)

    def test_repete_uma_vez_em_429_e_depois_desiste(self, monkeypatch):
        monkeypatch.setattr(agent.time, "sleep", lambda s: None)
        n = {"c": 0}

        def opener(req, timeout):
            n["c"] += 1
            raise urllib.error.HTTPError("u", 429, "limite", {}, io.BytesIO(b"rate"))

        with pytest.raises(agent.LLMError, match="429"):
            agent.call_claude("s", "u", model="m", key="k", opener=opener)
        assert n["c"] == 2

    def test_erro_de_autenticacao_nao_repete(self):
        n = {"c": 0}

        def opener(req, timeout):
            n["c"] += 1
            raise urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"invalid x-api-key"))

        with pytest.raises(agent.LLMError, match="401"):
            agent.call_claude("s", "u", model="m", key="k", opener=opener)
        assert n["c"] == 1


class TestRunOnce:
    def test_desligado_nao_faz_nada(self, tmp_path):
        assert agent.run_once(tmp_path, deps=Fake().deps(), now=lambda: NOW) == {"pulou": "desligado"}
        assert not (tmp_path / "decisions.jsonl").exists()

    def test_respeita_o_intervalo_e_grava_decisao_estado_e_livro(self, tmp_path):
        agent.save_config(tmp_path / "config.json", {"enabled": True, "interval_min": 10})
        f = Fake({"analise": "ok", "acoes": [abrir("NVDA")]})
        rec = agent.run_once(tmp_path, deps=f.deps(), now=lambda: NOW)
        assert rec["acoes"][0]["status"] == "executada"
        assert agent.read_decisions(tmp_path / "decisions.jsonl")[0]["acoes"][0]["ativo"] == "NVDA"
        assert json.loads((tmp_path / "book.json").read_text())["NVDA"]["opened_at"] == NOW
        st = json.loads((tmp_path / "state.json").read_text())
        assert st["ciclos"] == 1 and st["tokens"] == 1350
        assert agent.run_once(tmp_path, deps=f.deps(), now=lambda: NOW + 120) == {"pulou": "intervalo"}
        assert "acoes" in agent.run_once(tmp_path, deps=f.deps(), now=lambda: NOW + 700)  # passou o intervalo: roda

    def test_sem_chave_avisa_e_nao_roda(self, tmp_path):
        agent.save_config(tmp_path / "config.json", {"enabled": True})
        res = agent.run_once(tmp_path, now=lambda: NOW, env=lambda k, d="": d)
        assert "chave da IA" in res["erro"]
        assert "chave da IA" in json.loads((tmp_path / "state.json").read_text())["last_error"]

    def test_perda_do_dia_estourada_desliga_o_agente(self, tmp_path):
        agent.save_config(tmp_path / "config.json", {"enabled": True, "max_daily_loss": 2.0})
        agent.run_once(tmp_path, deps=Fake(pnl=-2.5).deps(), now=lambda: NOW)
        assert agent.load_config(tmp_path / "config.json")["enabled"] is False
        assert "desligado" in json.loads((tmp_path / "state.json").read_text())["last_error"]

    def test_diario_nao_cresce_sem_limite(self, tmp_path):
        p = tmp_path / "d.jsonl"
        for i in range(50):
            agent.append_decision(p, {"i": i}, keep=10)
        assert len(p.read_text().splitlines()) <= 20 and agent.read_decisions(p, 1)[0]["i"] == 49


class TestTradesDoAgente:
    def test_pnl_do_dia_e_ultimo_fechamento_so_das_trades_ia(self, tmp_path):
        p = tmp_path / "trades.csv"
        p.write_text("ts,origem,side,qty,entrada,saida,pnl,motivo\n"
                     "2026-11-18 10:00:00,kalshi/testnet:NVDA,1,1,1,1,-1.5,ia: tese\n"
                     "2026-11-18 11:00:00,kalshi/testnet:NVDA,1,1,1,1,0.5,ia: outra\n"
                     "2026-11-18 11:30:00,kalshi/testnet:AAPL,1,1,1,1,-9,stop\n"
                     "2026-11-17 11:00:00,kalshi/testnet:BTC,1,1,1,1,-4,ia: ontem\n")
        pnl, last = agent.trades_of_agent(p, 1_795_000_000)  # 2026-11-18 UTC
        assert pnl == pytest.approx(-1.0) and set(last) == {"NVDA", "BTC"}
        assert agent.trades_of_agent(None, NOW) == (0.0, {})
        assert agent.trades_of_agent(tmp_path / "nao.csv", NOW) == (0.0, {})


class TestApiDoAgente:
    """Rotas /api/agent* do painel: papeis, validacao e o que a tela recebe."""

    @pytest.fixture
    def srv(self, tmp_path, monkeypatch):
        import threading
        from http.server import ThreadingHTTPServer

        from quant import control
        from quant.auth import Auth

        monkeypatch.setenv("QUANT_AGENT_DIR", str(tmp_path / "agent"))
        monkeypatch.setenv("QUANT_AGENT_ENV", str(tmp_path / "agent.env"))
        monkeypatch.setenv("QUANT_TRADES_LOG", str(tmp_path / "trades.csv"))
        monkeypatch.setattr("quant.auth.ITERATIONS", 1000)
        auth = Auth(tmp_path / "auth")
        auth.setup("chefe", "senha-de-teste-1", "1.1.1.1")
        auth.create_user("oper", "senha-de-teste-2", "operador")
        auth.create_user("leitora", "senha-de-teste-3", "leitor")
        chamadas = []

        def run(cmd):
            chamadas.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "inactive\n", "stderr": ""})()

        srv = ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(tmp_path / "st.json", tmp_path / "K",
                                                                          tmp_path / "rt.env", run=run, auth=auth))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{srv.server_address[1]}", chamadas, tmp_path
        srv.shutdown()

    def call(self, base, path, method="GET", body=None, user="chefe", pw="senha-de-teste-1"):
        import urllib.request

        def go(url, m="GET", b=None, cookie=None):
            h = {"X-Quant-Control": "1", "Content-Type": "application/json"}
            if cookie:
                h["Cookie"] = cookie
            req = urllib.request.Request(url, data=None if b is None else json.dumps(b).encode(), method=m, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, json.loads(r.read() or b"{}"), r.headers
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}"), e.headers

        _, _, hdr = go(base + "/api/login", "POST", {"user": user, "password": pw})
        cookie = hdr["Set-Cookie"].split(";")[0]
        code, out, _ = go(base + path, method, body, cookie)
        return code, out

    def test_estado_inicial_desligado_e_sem_chave(self, srv, tmp_path, monkeypatch):
        monkeypatch.setenv("QUANT_CLAUDE_HOME", str(tmp_path / "sem-login"))  # nao depende do login da CLI da maquina
        base, _, _ = srv
        code, d = self.call(base, "/api/agent")
        assert code == 200 and d["config"]["enabled"] is False and d["chave"] is False and d["decisoes"] == []
        assert "claude-sonnet-5-5" in d["modelos"] and d["pnl_hoje"] == 0.0

    def test_operador_liga_e_desliga_mas_nao_muda_limites(self, srv):
        base, _, tmp = srv
        pw = ("oper", "senha-de-teste-2")
        assert self.call(base, "/api/agent/toggle", "POST", {"enabled": True}, *pw)[0] == 200
        assert agent.load_config(tmp / "agent" / "config.json")["enabled"] is True
        assert self.call(base, "/api/agent/toggle", "POST", {"enabled": True, "max_usd": 99}, *pw)[0] == 400
        assert self.call(base, "/api/agent/config", "POST", {"max_usd": 50}, *pw)[0] == 403

    def test_leitor_so_ve(self, srv):
        base, _, _ = srv
        pw = ("leitora", "senha-de-teste-3")
        assert self.call(base, "/api/agent", "GET", None, *pw)[0] == 200
        assert self.call(base, "/api/agent/toggle", "POST", {"enabled": True}, *pw)[0] == 403
        assert self.call(base, "/api/agent/run", "POST", {}, *pw)[0] == 403

    def test_admin_muda_limites_validados(self, srv):
        base, _, tmp = srv
        code, out = self.call(base, "/api/agent/config", "POST", {"max_usd": 25, "long_only": False})
        assert code == 200 and out["config"]["max_usd"] == 25.0 and out["config"]["long_only"] is False
        assert self.call(base, "/api/agent/config", "POST", {"max_usd": 5000})[0] == 400
        assert self.call(base, "/api/agent/config", "POST", {"chave": "x"})[0] == 400

    def test_rodar_agora_dispara_a_unit_do_ciclo_forcado(self, srv):
        base, chamadas, _ = srv
        assert self.call(base, "/api/agent/run", "POST", {}, "oper", "senha-de-teste-2")[0] == 200
        assert ["systemctl", "start", "--no-block", "quant-agent-agora.service"] in chamadas

    def test_decisoes_e_livro_aparecem_na_tela(self, srv):
        base, _, tmp = srv
        agent.append_decision(tmp / "agent" / "decisions.jsonl", {"t": 1, "analise": "x", "acoes": []})
        (tmp / "agent" / "book.json").write_text(json.dumps({"NVDA": {"opened_at": 5, "reason": "r"}}))
        (tmp / "agent.env").write_text("ANTHROPIC_API_KEY=sk\n")
        d = self.call(base, "/api/agent")[1]
        assert d["decisoes"][0]["analise"] == "x" and d["livro"]["NVDA"]["reason"] == "r" and d["chave"] is True
        assert "sk" not in json.dumps(d)  # o painel so sabe SE a chave existe, nunca o valor

    def test_unidades_e_polkit(self):
        from pathlib import Path

        dep = Path(__file__).resolve().parents[1] / "deploy"
        assert "quant.agent run --force" in (dep / "quant-agent-agora.service").read_text()
        assert "quant.agent run\n" in (dep / "quant-agent.service").read_text()
        assert "quant-agent-agora.service" in (dep / "50-quant-control.rules").read_text()
        assert "agent.env" not in (dep / "quant-control.service").read_text()  # o painel web nao carrega a chave da IA


class TestCli:
    """Backend pela CLI do Claude (``claude -p``): sem chave de API, so o login."""

    def fake(self, stdout, code=0):
        calls = []

        def run(cmd, **kw):
            calls.append((cmd, kw))
            return types.SimpleNamespace(stdout=stdout, stderr="", returncode=code)
        return run, calls

    def test_devolve_a_decisao_estruturada_e_o_uso(self, tmp_path):
        out = {"analise": "parado", "acoes": []}
        run, calls = self.fake(json.dumps({"structured_output": out, "usage": {"input_tokens": 7, "output_tokens": 3}}))
        got, uso = agent.call_cli("sys", "user", model="claude-haiku-5-5", home=tmp_path, run=run)
        assert got == out and uso == {"input_tokens": 7, "output_tokens": 3}
        cmd, kw = calls[0]
        assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""  # sem ferramentas: so devolve o JSON
        assert kw["input"] == "user" and kw["env"]["HOME"] == str(tmp_path)

    def test_aceita_decisao_em_result_como_json(self, tmp_path):
        run, _ = self.fake(json.dumps({"result": '{"analise": "x", "acoes": []}'}))
        assert agent.call_cli("s", "u", model="m", home=tmp_path, run=run)[0]["analise"] == "x"

    def test_erro_da_cli_e_saida_sem_decisao_viram_llmerror(self, tmp_path):
        for stdout in (json.dumps({"is_error": True, "result": "not logged in"}), "nao e json",
                       json.dumps({"result": "texto solto"})):
            run, _ = self.fake(stdout)
            with pytest.raises(agent.LLMError):
                agent.call_cli("s", "u", model="m", home=tmp_path, run=run)

    def test_sem_login_o_ciclo_nao_roda(self, tmp_path):
        env = {"QUANT_AGENT_BACKEND": "cli", "QUANT_CLAUDE_HOME": str(tmp_path)}.get
        agent.save_config(tmp_path / "config.json", {"enabled": True})
        res = agent.run_once(tmp_path, env=env)
        assert "login da CLI" in res["erro"]
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / ".credentials.json").write_text("{}")
        assert agent.cli_ready(env)
