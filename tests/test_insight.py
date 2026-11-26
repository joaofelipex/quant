"""Telas de analise: funil da IA, radar do robo, fluxo por ativo e tabela de estudos."""
import json

import pytest

from quant import flow, insight

NOW = 1_795_000_000.0


def foto(asset, imb=0.2, mid=100.0):
    return {"asset": asset, "mark": mid, "bid": mid - 0.1, "ask": mid + 0.1, "spread_bps": 20.0, "imb_25": imb,
            "imb_100": imb, "imb_top5": 0.0, "bid_usd_100": 1.0, "ask_usd_100": 1.0}


def pastas(tmp_path):
    flow.write_rows([foto("BTC"), foto("GOLD", -0.5)], tmp_path / "flow", int(NOW - 120))
    flow.write_rows([foto("BTC", 0.4, 101.0)], tmp_path / "flow", int(NOW - 60))
    decisao = {"t": int(NOW - 90), "model": "m", "sombra": True, "analise": "x", "universo": 145, "fotos": 40,
               "candidatos": ["BTC", "GOLD"], "leitura": [{"ativo": "BTC", "ret_5m_bps": 3}, {"ativo": "GOLD"}],
               "acoes": [{"acao": "abrir", "ativo": "BTC", "status": "recusada", "why": "alvo baixo"},
                         {"acao": "abrir", "ativo": "GOLD", "status": "sombra", "motivo": "fluxo"}]}
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "decisions.jsonl").write_text(json.dumps(decisao) + "\nlixo\n")
    for nome, close, er, entry in (("BTC", 99.0, 0.7, None), ("ETH", 90.0, 0.9, None), ("SOL", 50.0, 0.1, {"side": 1})):
        st = {"last_bar": "2026-11-22 10:00:00", "entry": entry, "risk": {"halted": False},
              "leitura": {"close": close, "canal_alta": 100.0, "canal_baixa": 80.0, "er": er, "tendencia": 1,
                          "sinal": 0, "resultado": "ok"}}
        (tmp_path / f"live_state.{nome}.json").write_text(json.dumps(st))
    return tmp_path


def test_funil_da_ia_com_o_destino_de_cada_candidato(tmp_path):
    p = pastas(tmp_path)
    r = insight.live(p / "agent", p, p / "flow", p / "nada.json", ["BTC", "ETH", "SOL", "XRP"], 0.4, now=NOW)
    ia = r["ia"]
    assert ia["funil"] == {"universo": 145, "fotos": 40, "candidatos": 2, "pedidos": 2, "aceitos": 1}
    assert ia["candidatos"][0]["status"] == "recusada" and ia["candidatos"][0]["porque"] == "alvo baixo"
    assert ia["candidatos"][0]["ret_5m_bps"] == 3 and ia["ha_s"] == 90
    fontes = {f["nome"]: f for f in r["fontes"]}
    assert fontes["fotos do livro"]["idade_s"] == 60 and fontes["métricas da conta"]["idade_s"] is None


def test_radar_poe_posicao_primeiro_depois_quem_esta_perto_de_romper(tmp_path):
    p = pastas(tmp_path)
    r = insight.live(p / "agent", p, p / "flow", p / "x", ["ETH", "BTC", "SOL", "XRP"], 0.4, now=NOW)["robo"]
    assert [x["ativo"] for x in r] == ["SOL", "BTC", "ETH", "XRP"]
    btc = r[1]
    assert btc["falta_alta_pct"] == pytest.approx(100 / 99 * 100 - 100) and btc["er_ok"] and btc["fluxo"] == 0.4


def test_serie_do_fluxo_de_um_ativo_com_as_decisoes(tmp_path):
    p = pastas(tmp_path)
    s = insight.flow_series(p / "flow", p / "agent", "BTC", 1, now=NOW)
    assert [round(x[1], 1) for x in s["serie"]] == [100.0, 101.0] and s["decisoes"][0]["porque"] == "alvo baixo"
    with pytest.raises(ValueError):
        insight.flow_series(p / "flow", p / "agent", "../etc", now=NOW)


def test_serie_longa_e_reduzida(tmp_path):
    for i in range(50):
        flow.write_rows([foto("BTC")], tmp_path, int(NOW - 3000 + i * 60))
    assert len(insight.flow_series(tmp_path, tmp_path, "BTC", 1, now=NOW, points=10)["serie"]) <= 10


def test_sem_arquivos_nao_quebra(tmp_path):
    r = insight.live(tmp_path, tmp_path, tmp_path, tmp_path / "m", [], 0.4, now=NOW)
    assert r["ia"] is None and r["robo"] == [] and all(f["idade_s"] is None for f in r["fontes"])


def test_estudos_vem_da_tabela_do_readme_do_repo():
    estudos = insight.research()
    nomes = {e["nome"] for e in estudos}
    assert {"regras_historico", "vela_30min", "trend_19cripto"} <= nomes
    por = {e["nome"]: e for e in estudos}
    assert por["vela_30min"]["tom"] == "bad" and por["trend_19cripto"]["tom"] == "warn"
    assert "**" not in por["vela_30min"]["status"]
