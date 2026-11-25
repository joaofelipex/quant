"""Leitura de fluxo: fotos do livro, gravacao e o estudo de poder preditivo (sem rede)."""
import numpy as np
import pandas as pd
import pytest

from quant import flow


def book(bids, asks):
    return {"bids": [[str(p), str(q)] for p, q in bids], "asks": [[str(p), str(q)] for p, q in asks]}


class TestFeatures:
    def test_desequilibrio_para_o_lado_com_mais_dinheiro(self):
        f = flow.features(book([(99.9, 300), (99.8, 300)], [(100.1, 50), (100.2, 50)]), mark=100.0)
        assert f["imb_100"] > 0.6 and f["imb_top5"] > 0.6 and f["bid"] == 99.9 and f["ask"] == 100.1
        assert f["spread_bps"] == pytest.approx(20.0, abs=0.1)

    def test_lado_vendedor_forte_da_negativo(self):
        f = flow.features(book([(99.9, 50)], [(100.1, 400)]), mark=100.0)
        assert f["imb_100"] < -0.7

    def test_oferta_solta_longe_do_mercado_nao_entra_na_conta(self):
        # o caso real do ALUMINUM: um ask perdido muito longe do preco
        f = flow.features(book([(99.9, 100)], [(100.1, 100), (700.0, 99999)]), mark=100.0)
        assert abs(f["imb_100"]) < 0.05

    def test_livro_vazio_ou_longe_do_preco_justo_nao_gera_foto(self):
        assert flow.features(book([], [(100.1, 1)]), 100.0) is None
        assert flow.features(book([(50.0, 10)], [(60.0, 10)]), 100.0) is None  # meio 55 vs mark 100

    def test_ignora_niveis_malformados(self):
        f = flow.features({"bids": [["x", "1"], [99.9, 10], None], "asks": [["100.1", "10"]]}, 100.0)
        assert f is not None and f["bid"] == 99.9


class TestRecord:
    def fetch(self, url):
        if url.endswith("/orderbook"):
            return {"orderbook": book([(99.9, 10)], [(100.1, 30)])}
        if "KXBOOMPERP1" in url:
            raise OSError("fora do ar")
        return {"market": {"price": "100.0"}}

    def test_grava_um_csv_por_dia_e_pula_o_que_falha(self, tmp_path, monkeypatch):
        monkeypatch.setattr(flow.assets_mod, "ticker", lambda a: f"KX{a}PERP1")
        n = flow.record(["AAA", "BOOM", "BBB"], tmp_path, fetch=self.fetch, now=lambda: 1_795_000_000, workers=3)
        assert n == 2
        files = list(tmp_path.glob("*.csv"))
        assert len(files) == 1 and files[0].name == "2026-11-18.csv"
        df = pd.read_csv(files[0])
        assert sorted(df["asset"]) == ["AAA", "BBB"] and list(df.columns) == flow.FIELDS
        flow.record(["AAA"], tmp_path, fetch=self.fetch, now=lambda: 1_795_000_060)
        assert len(pd.read_csv(files[0])) == 3  # acrescenta, sem repetir o cabecalho

    def test_nenhuma_foto_nao_cria_arquivo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(flow.assets_mod, "ticker", lambda a: f"KX{a}PERP1")
        assert flow.record(["BOOM"], tmp_path, fetch=self.fetch) == 0 and not list(tmp_path.glob("*.csv"))


def synthetic(predictive: bool, n=600, seed=1):
    """Fotos de 1 min de 3 ativos; se ``predictive``, o retorno do minuto seguinte segue o desequilibrio de agora."""
    rng = np.random.default_rng(seed)
    rows = []
    for a in ("AAA", "BBB", "CCC"):
        mid, t0 = 100.0, 1_795_000_000
        for i in range(n):
            imb = float(rng.uniform(-1, 1))
            rows.append({"ts": t0 + 60 * i, "asset": a, "bid": mid * 0.9999, "ask": mid * 1.0001, "imb_100": imb,
                         "imb_25": imb, "imb_top5": imb, "spread_bps": 2.0})
            drift = 8.0 * imb if predictive else 0.0  # bps por minuto
            mid *= 1 + (drift + rng.normal(0, 3.0)) / 1e4
    return pd.DataFrame(rows)


class TestEstudo:
    def test_acha_o_sinal_quando_ele_existe(self):
        r = flow.evaluate(synthetic(True), "imb_100", horizons=(1,))
        h = r["horizontes"][1]
        assert h["ic"] > 0.3 and h["z"] > 3 and h["liquido_bps"] > 0 and h["veredito"] == "tem sinal apos custo"
        assert h["quintis_bps"][-1] > h["quintis_bps"][0]

    def test_nao_inventa_sinal_em_ruido(self):
        r = flow.evaluate(synthetic(False), "imb_100", horizons=(1, 5))
        for h in r["horizontes"].values():
            assert h["veredito"] == "sem vantagem comprovada" and abs(h["z"]) < 3.5

    def test_poucos_dados_dizem_que_faltam_dados(self):
        r = flow.evaluate(synthetic(True, n=10), "imb_100", horizons=(1,))
        assert r["horizontes"][1]["veredito"] == "poucos dados"

    def test_retorno_futuro_so_conta_se_a_foto_veio_no_minuto_certo(self):
        df = synthetic(True, n=20)
        df = df[df["ts"] != df["ts"].unique()[5]]  # buraco de 1 minuto em todos os ativos
        d = flow.with_forward_returns(df, (1,))
        antes = d[d["ts"] == df["ts"].unique()[4]]  # a foto seguinte (indice 6) veio 2 min depois
        assert antes["ret_1m"].isna().all()

    def test_cli_sem_fotos(self, tmp_path, capsys):
        assert flow.main(["study", str(tmp_path)]) == 1
        assert "sem fotos" in capsys.readouterr().out
