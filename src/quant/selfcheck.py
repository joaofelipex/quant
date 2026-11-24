"""Rotina automatica de testes e verificacoes da VM (sem LLM, sem rede, sem poder para alterar servicos).

    QUANT_SELFCHECK=/var/lib/quant/selfcheck.json QUANT_PORT_LOG=... python -m quant.selfcheck

Roda a suite pytest, confere a saude dos servicos e do paper, avalia o paper da carteira (retorno, Sharpe, drawdown) e
grava um relatorio JSON que o painel de controle mostra. Le arquivos e roda pytest; nao mexe em servico nem le chaves.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS_ACTIVE = ("quant-control", "quant-portfolio.timer", "nginx")
MIN_DAYS_FOR_VERDICT = 90  # abaixo disso o Sharpe do paper e ruido; a regra do repo pede 12 meses


def _run(cmd: list[str], timeout: float = 15, cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def run_pytest(root: Path = ROOT, timeout: float = 900) -> dict:
    """Roda a suite e devolve contagens. ``-p no:cacheprovider``: nao escreve nada no diretorio do projeto."""
    t0 = time.time()
    rc, out = _run([sys.executable, "-m", "pytest", "-q", "-W", "ignore", "-p", "no:cacheprovider"],
                   timeout=timeout, cwd=root)
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|error|errors|skipped)", out)}
    failed = counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)
    names = re.findall(r"^FAILED (\S+)", out, re.M)[:10]
    return {"ok": rc == 0 and failed == 0, "passed": counts.get("passed", 0), "failed": failed,
            "skipped": counts.get("skipped", 0), "seconds": round(time.time() - t0, 1), "failures": names,
            "tail": out.splitlines()[-1] if out else ""}


def health(kill_file: Path, port_log: Path, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    checks = []
    for unit in UNITS_ACTIVE:
        rc, out = _run(["systemctl", "is-active", unit])
        checks.append({"name": f"{unit} ativo", "ok": out.strip() == "active", "detail": out.strip() or "?"})
    checks.append({"name": "sem arquivo KILL", "ok": not kill_file.exists(), "detail": str(kill_file)})
    try:
        age_h = (now - port_log.stat().st_mtime) / 3600
        checks.append({"name": "log do paper atualizado (< 30 h)", "ok": age_h < 30, "detail": f"{age_h:.1f} h"})
    except OSError:
        checks.append({"name": "log do paper atualizado (< 30 h)", "ok": False, "detail": "sem arquivo"})
    st = os.statvfs("/") if hasattr(os, "statvfs") else None
    if st:
        free = st.f_bavail / st.f_blocks
        checks.append({"name": "disco com > 10% livre", "ok": free > 0.10, "detail": f"{free:.0%} livre"})
    return checks


def evaluate_paper(port_log: Path) -> dict | None:
    """Estatisticas do paper a partir do CSV diario. NAO substitui a regra do repo (12 meses, 5 criterios)."""
    try:
        rows = list(csv.DictReader(port_log.read_text().splitlines()))
    except OSError:
        return None
    pnl = []
    for r in rows:
        try:
            x = float(r["pnl"])
            if not math.isnan(x):
                pnl.append(x)
        except (KeyError, ValueError):
            pass
    if not rows:
        return None
    eq = [float(r["equity"]) for r in rows if r.get("equity") not in (None, "", "nan")]
    peak, mdd = 0.0, 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    n = len(pnl)
    mean = sum(pnl) / n if n else 0.0
    var = sum((x - mean) ** 2 for x in pnl) / (n - 1) if n > 1 else 0.0
    sharpe = mean / math.sqrt(var) * math.sqrt(365) if var > 0 else None
    verdict = ("amostra curta: ainda sem conclusao" if n < MIN_DAYS_FOR_VERDICT else
               "Sharpe positivo ate agora" if sharpe and sharpe > 0 else "Sharpe nao positivo ate agora")
    return {"days": len(rows), "equity": eq[-1] if eq else None, "ret_total": (eq[-1] - 1) if eq else None,
            "sharpe": sharpe, "max_dd": mdd, "verdict": verdict,
            "regra_do_repo": "reavaliar com 5 criterios apos 12 meses"}


def build_report(*, with_tests: bool = True, root: Path = ROOT) -> dict:
    kill = Path(os.environ.get("QUANT_KILL_FILE", "/var/lib/quant/KILL"))
    port_log = Path(os.environ.get("QUANT_PORT_LOG", "portfolio_log.csv"))
    tests = run_pytest(root) if with_tests else None
    checks = health(kill, port_log)
    ok = all(c["ok"] for c in checks) and (tests is None or tests["ok"])
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok, "tests": tests, "checks": checks,
            "paper": evaluate_paper(port_log)}


def write_report(report: dict, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=1))
    tmp.replace(path)


def main() -> int:
    path = Path(os.environ.get("QUANT_SELFCHECK", "selfcheck.json"))
    report = build_report()
    write_report(report, path)
    t = report["tests"]
    print(f"selfcheck {'OK' if report['ok'] else 'FALHOU'}: testes {t['passed']} ok / {t['failed']} falhas; "
          f"checks {sum(c['ok'] for c in report['checks'])}/{len(report['checks'])} -> {path}", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
