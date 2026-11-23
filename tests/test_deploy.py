"""Guarda de regressao dos arquivos de deploy: erros aqui so apareceriam na VM, com a conta ou o painel expostos."""
import re
from pathlib import Path

import pandas as pd
from test_live import FakeFeed, PaperExecutor, sig_fn

from quant.live.risk import RiskLimits, RiskManager
from quant.live.runner import Runner

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def directives(text: str) -> list[str]:
    """Linhas de configuracao sem comentarios nem vazias."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def server_blocks(conf: str) -> list[str]:
    """Blocos `server { ... }` de nivel 1 (contagem de chaves; comentarios removidos)."""
    conf = "\n".join(ln.split("#")[0] for ln in conf.splitlines())
    blocks, depth, start = [], 0, None
    for m in re.finditer(r"[{}]|\bserver\s*\{", conf):
        tok = m.group()
        if tok.startswith("server") and depth == 0:
            start, depth = m.start(), 1
        elif tok == "{" and depth:
            depth += 1
        elif tok == "}" and depth:
            depth -= 1
            if depth == 0:
                blocks.append(conf[start:m.end()])
    return blocks


# ---- 1. o paper da carteira nao ve as chaves da corretora -----------------------------------------------------
def test_portfolio_nao_le_o_env_com_chaves():
    unit = read("quant-portfolio.service")
    assert "quant-live.env" not in "\n".join(directives(unit))
    assert "EnvironmentFile=/etc/quant-portfolio.env" in directives(unit)


def test_env_do_portfolio_nao_tem_chave_de_corretora():
    env = "\n".join(directives(read("quant-portfolio.env.example")))
    for proibido in ("BINANCE", "SECRET", "QUANT_MODE", "ALLOW_MAINNET"):
        assert proibido not in env
    assert "QUANT_PORT_STATE=" in env and "QUANT_SITE_DIR=" in env


def test_as_chaves_so_existem_no_env_do_runner():
    assert "BINANCE_API_KEY=" in read("quant-live.env.example")
    assert "EnvironmentFile=/etc/quant-live.env" in directives(read("quant-live.service"))


# ---- 2. nginx: senha e painel so em HTTPS --------------------------------------------------------------------
def test_final_porta_80_nao_serve_painel_nem_pede_senha():
    blocks = server_blocks(read("nginx-quant.conf"))
    http = [b for b in blocks if re.search(r"listen\s+(\[::\]:)?80\b", b)]
    https = [b for b in blocks if "443 ssl" in b]
    assert len(http) == 1 and len(https) == 1
    assert "auth_basic" not in http[0] and "/var/www/quant" not in http[0]
    assert "return 301 https://" in http[0] and "acme-challenge" in http[0]
    assert "auth_basic_user_file" in https[0] and "ssl_certificate_key" in https[0]
    assert "TLSv1.2 TLSv1.3" in https[0] and "limit_req zone=quant_login" in https[0]


def test_painel_serve_a_pagina_inicial_pelo_index():
    """Regressao achada na VM real: 'try_files $uri =404' devolvia 404 em '/', o painel nunca abria."""
    https = [b for b in server_blocks(read("nginx-quant.conf")) if "443 ssl" in b][0]
    assert "index index.html" in https
    m = re.search(r"try_files\s+([^;]+);", https)
    assert m and "$uri/" in m.group(1), "try_files sem $uri/ nao resolve '/' para o index"


def test_bootstrap_so_responde_ao_desafio_do_certbot():
    blocks = server_blocks(read("nginx-quant-bootstrap.conf"))
    assert len(blocks) == 1
    b = blocks[0]
    assert "443" not in b and "auth_basic" not in b and "/var/www/quant" not in b and "index" not in b
    assert "acme-challenge" in b and "return 404" in b


# ---- 3. kill-switch x systemd ---------------------------------------------------------------------------------
def test_live_service_nao_religa_apos_o_kill_switch():
    unit = directives(read("quant-live.service"))
    assert "Restart=on-failure" in unit and "Restart=always" not in unit
    kill_env = re.search(r"QUANT_KILL_FILE=(\S+)", read("quant-live.env.example")).group(1)
    assert f"ConditionPathExists=!{kill_env}" in unit  # servico nem inicia com o arquivo KILL presente
    assert any(ln.startswith("StartLimitBurst=") for ln in unit)


def test_runner_retorna_quando_ha_kill_para_o_processo_sair_com_codigo_0(tmp_path):
    ex = PaperExecutor(slippage=0.0, fee_rate=0.0)
    risk = RiskManager(RiskLimits(max_qty=1.0, max_daily_loss=1000.0))
    kill = tmp_path / "KILL"
    kill.write_text("")
    r = Runner(FakeFeed([(100, 101, 99, 100)] * 4), ex, risk, sig_fn({}), qty=1.0,
               state_path=tmp_path / "s.json", kill_file=kill, now_fn=lambda: pd.Timestamp("2026-03-02 10:00"))
    assert r.run() is None  # volta em vez de ficar em loop: processo encerra e o systemd nao religa (exit 0)
    assert risk.halted and "kill-switch" in risk.halt_reason


def test_servicos_tem_privilegio_minimo():
    for name in ("quant-live.service", "quant-portfolio.service"):
        unit = directives(read(name))
        for d in ("NoNewPrivileges=yes", "ProtectSystem=strict", "PrivateTmp=yes", "StateDirectory=quant"):
            assert d in unit, f"{name} sem {d}"
