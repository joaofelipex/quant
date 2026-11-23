import json

import pandas as pd

from quant import dashboard

RESULTS = """# x

## Veredito: **REPROVADA**
- [ ] 1. Sharpe <script>alert(1)</script>
- [x] 3. custos x2
"""


def _log():
    return pd.DataFrame({
        "date": pd.date_range("2026-11-23", periods=3), "equity": [0.9998, 1.001, 1.0005],
        "pnl": [0.0, 0.0013, -0.0004], "funding": [0.0, -0.0001, -0.0001], "cost": [-0.0002, -0.0001, 0.0],
        "turnover": [0.3, 0.1, 0.0], "gross": [0.33, 0.35, 0.35]})


def test_painel_com_dados_e_sem_injecao(tmp_path):
    res = tmp_path / "r.md"
    res.write_text(RESULTS, encoding="utf-8")
    state = {"weights": {"BTCUSDT": -0.07, "ETHUSDT": 0.03, "ADAUSDT": 0.0}}
    page = dashboard.build_html(state, _log(), res)
    assert "PAPER" in page and "REPROVADA" in page and "vendido" in page and "comprado" in page
    assert "<script>" not in page and "&lt;script&gt;" in page  # texto de arquivo e escapado
    assert "<polyline" in page  # grafico de equity
    assert 'content="noindex,nofollow"' in page


def test_painel_sem_log_nao_quebra(tmp_path):
    page = dashboard.build_html(None, pd.DataFrame(), tmp_path / "nao_existe.md")
    assert "Aguardando o primeiro disparo" in page


def test_main_escreve_index(tmp_path, monkeypatch):
    log = _log()
    log.to_csv(tmp_path / "log.csv", index=False)
    (tmp_path / "s.json").write_text(json.dumps({"weights": {"BTCUSDT": 0.01}}))
    monkeypatch.setenv("QUANT_PORT_LOG", str(tmp_path / "log.csv"))
    monkeypatch.setenv("QUANT_PORT_STATE", str(tmp_path / "s.json"))
    monkeypatch.setattr("sys.argv", ["dashboard", "--out", str(tmp_path / "site")])
    dashboard.main()
    assert (tmp_path / "site" / "index.html").exists()
