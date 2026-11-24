"""Rotina de autoverificacao da VM: contagem de testes, saude, avaliacao do paper e gravacao atomica do relatorio."""
import json

import pytest

from quant import selfcheck


def test_run_pytest_conta_passou_e_falhou(tmp_path):
    (tmp_path / "test_a.py").write_text("def test_ok():\n    assert True\n\ndef test_ruim():\n    assert False\n")
    r = selfcheck.run_pytest(tmp_path, timeout=120)
    assert r["passed"] == 1 and r["failed"] == 1 and r["ok"] is False
    assert any("test_ruim" in f for f in r["failures"])
    (tmp_path / "test_a.py").write_text("def test_ok():\n    assert True\n")
    assert selfcheck.run_pytest(tmp_path, timeout=120)["ok"] is True


def test_saude_marca_kill_e_log_velho(tmp_path, monkeypatch):
    monkeypatch.setattr(selfcheck, "_run", lambda *a, **k: (0, "active"))
    kill, log = tmp_path / "KILL", tmp_path / "p.csv"
    log.write_text("date,equity,pnl\n")
    by = {c["name"]: c for c in selfcheck.health(kill, log)}
    assert by["sem arquivo KILL"]["ok"] and by["log do paper atualizado (< 30 h)"]["ok"]
    kill.write_text("x")
    assert not {c["name"]: c for c in selfcheck.health(kill, log)}["sem arquivo KILL"]["ok"]
    old = log.stat().st_mtime + 40 * 3600
    assert not {c["name"]: c for c in selfcheck.health(kill, log, now=old)}["log do paper atualizado (< 30 h)"]["ok"]
    assert not {c["name"]: c for c in selfcheck.health(kill, tmp_path / "nao.csv")}[
        "log do paper atualizado (< 30 h)"]["ok"]


def test_servico_inativo_reprova_a_checagem(tmp_path, monkeypatch):
    monkeypatch.setattr(selfcheck, "_run", lambda *a, **k: (3, "inactive"))
    assert not any(c["ok"] for c in selfcheck.health(tmp_path / "K", tmp_path / "p.csv") if c["name"].endswith("ativo"))


def test_avaliacao_do_paper_amostra_curta_e_drawdown(tmp_path):
    log = tmp_path / "p.csv"
    log.write_text("date,equity,pnl\n2026-11-23,1.0,0.0\n2026-11-24,1.1,0.1\n2026-11-25,0.99,-0.1\n")
    ev = selfcheck.evaluate_paper(log)
    assert ev["days"] == 3 and ev["equity"] == pytest.approx(0.99) and ev["max_dd"] == pytest.approx(0.99 / 1.1 - 1)
    assert "amostra curta" in ev["verdict"]
    assert selfcheck.evaluate_paper(tmp_path / "nao_existe.csv") is None


def test_relatorio_sem_testes_e_gravacao_atomica(tmp_path, monkeypatch):
    monkeypatch.setattr(selfcheck, "_run", lambda *a, **k: (0, "active"))
    monkeypatch.setenv("QUANT_KILL_FILE", str(tmp_path / "KILL"))
    monkeypatch.setenv("QUANT_PORT_LOG", str(tmp_path / "p.csv"))
    (tmp_path / "p.csv").write_text("date,equity,pnl\n2026-11-23,1.0,0.0\n")
    rep = selfcheck.build_report(with_tests=False)
    assert rep["tests"] is None and rep["ok"] is True
    out = tmp_path / "selfcheck.json"
    selfcheck.write_report(rep, out)
    assert json.loads(out.read_text())["ok"] is True and not (tmp_path / "selfcheck.tmp").exists()


def test_addopts_q_do_projeto_nao_esconde_o_resumo(tmp_path):
    # como o pyproject do repo: com -q duplicado o pytest nao imprime o resumo
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    (tmp_path / "test_a.py").write_text("def test_ok():\n    assert True\n")
    r = selfcheck.run_pytest(tmp_path, timeout=120)
    assert r["passed"] == 1 and r["ok"] is True


def test_zero_testes_coletados_nao_e_ok(tmp_path):
    assert selfcheck.run_pytest(tmp_path, timeout=120)["ok"] is False
