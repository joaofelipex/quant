"""Painel estatico (um unico index.html, sem JS nem libs externas) do paper trading da carteira tsmom_cripto.

    QUANT_PORT_STATE=... QUANT_PORT_LOG=... python -m quant.dashboard --out /var/www/quant

Gerado depois de cada disparo diario do paper (ver deploy/quant-portfolio.service). Le so arquivos locais; todo texto vindo
de arquivo passa por ``html.escape``. O painel mostra o paper, que NAO envia ordens: nao e extrato de conta real.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--mute:#5d6674;--line:#e3e6ea;--accent:#1f6feb;--short:#c2410c;--ok:#15803d;--bad:#b91c1c}
@media(prefers-color-scheme:dark){:root{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--mute:#8b949e;--line:#2b323c;--accent:#58a6ff;--short:#fb923c;--ok:#4ade80;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:920px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
.top{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between}
.badge{font-size:12px;border:1px solid var(--line);border-radius:99px;padding:2px 10px;color:var(--mute)}
.sub{color:var(--mute);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.k{font-size:12px;color:var(--mute)}.v{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.pos{color:var(--ok)}.neg{color:var(--bad)}
svg{width:100%;height:auto;display:block}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}
th{color:var(--mute);font-weight:500;font-size:12px}
.w{display:grid;grid-template-columns:70px 1fr 120px;gap:8px;align-items:center;padding:4px 0;font-size:14px}
.track{position:relative;height:14px;background:var(--line);border-radius:4px}
.bar{position:absolute;top:0;height:100%;border-radius:4px}
.mid{position:absolute;left:50%;top:-2px;height:18px;width:1px;background:var(--mute)}
.crit{list-style:none;padding:0;margin:8px 0 0}.crit li{padding:4px 0;border-bottom:1px solid var(--line)}
.crit .y{color:var(--ok)}.crit .n{color:var(--bad)}
.note{color:var(--mute);font-size:13px;margin-top:20px}
@media(max-width:520px){.w{grid-template-columns:56px 1fr 96px}.v{font-size:19px}}
"""


def _pct(x: float, d: int = 2) -> str:
    return f"{x * 100:+.{d}f}%".replace(".", ",")


def _cls(x: float) -> str:
    return "pos" if x > 0 else "neg" if x < 0 else ""


def read_log(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def equity_svg(df: pd.DataFrame) -> str:
    w, h, pad_l, pad_r, pad_t, pad_b = 720, 220, 52, 12, 12, 26
    y = df["equity"].to_numpy()
    lo, hi = min(y.min(), 1.0), max(y.max(), 1.0)
    span = (hi - lo) or 0.01
    lo, hi = lo - span * 0.1, hi + span * 0.1

    def sx(i: int) -> float:
        return pad_l + (w - pad_l - pad_r) * (i / max(len(y) - 1, 1))

    def sy(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(y))
    base = sy(1.0)
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Equity do paper ao longo do tempo">',
        f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{base:.1f}" y2="{base:.1f}" stroke="var(--line)" stroke-dasharray="4 4"/>',
        f'<text x="{pad_l - 6}" y="{base + 4:.1f}" text-anchor="end" font-size="11" fill="var(--mute)">1,000</text>',
        f'<text x="{pad_l - 6}" y="{pad_t + 8}" text-anchor="end" font-size="11" fill="var(--mute)">{hi:.3f}</text>'.replace(".", ","),
        f'<text x="{pad_l - 6}" y="{h - pad_b}" text-anchor="end" font-size="11" fill="var(--mute)">{lo:.3f}</text>'.replace(".", ","),
    ]
    if len(y) > 1:
        parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>')
    parts.append(f'<circle cx="{sx(len(y) - 1):.1f}" cy="{sy(y[-1]):.1f}" r="4" fill="var(--accent)"/>')
    d0, d1 = df["date"].iloc[0].strftime("%d/%m/%Y"), df["date"].iloc[-1].strftime("%d/%m/%Y")
    parts.append(f'<text x="{pad_l}" y="{h - 6}" font-size="11" fill="var(--mute)">{d0}</text>')
    parts.append(f'<text x="{w - pad_r}" y="{h - 6}" text-anchor="end" font-size="11" fill="var(--mute)">{d1}</text></svg>')
    return "".join(parts)


def weights_html(weights: dict[str, float]) -> str:
    scale = max([abs(v) for v in weights.values()] + [0.05])
    rows = []
    for sym, w in weights.items():
        half = abs(w) / scale * 50
        left, color = (50, "var(--accent)") if w >= 0 else (50 - half, "var(--short)")
        side = "comprado" if w > 1e-9 else "vendido" if w < -1e-9 else "zerado"
        rows.append(
            f'<div class="w"><span>{html.escape(sym[:-4])}</span><div class="track"><div class="mid"></div>'
            f'<div class="bar" style="left:{left:.1f}%;width:{half:.1f}%;background:{color}"></div></div>'
            f'<span>{_pct(w, 1)} <span class="sub">{side}</span></span></div>'
        )
    return "".join(rows)


def criteria_html(results_md: Path) -> str:
    if not results_md.exists():
        return '<p class="sub">Relatorio do estudo nao encontrado.</p>'
    text = results_md.read_text(encoding="utf-8")
    verdict = next((ln for ln in text.splitlines() if ln.startswith("## Veredito")), "")
    crit = [ln for ln in text.splitlines() if ln.startswith("- [")]
    items = "".join(
        f'<li class="{"y" if ln.startswith("- [x]") else "n"}">{"OK" if ln.startswith("- [x]") else "falhou"} &middot; '
        f"{html.escape(ln[6:].strip())}</li>" for ln in crit
    )
    v = html.escape(verdict.replace("## Veredito:", "").replace("*", "").strip())
    return f'<p>Veredito do estudo pre-registrado: <strong>{v}</strong></p><ul class="crit">{items}</ul>'


def build_html(state: dict | None, log: pd.DataFrame, results_md: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%d/%m/%Y %H:%M UTC")
    body = [
        '<div class="top"><h1>quant &middot; carteira tsmom_cripto</h1><span class="badge">PAPER &middot; sem ordens reais</span></div>',
        f'<div class="sub">Atualizado em {stamp}. Estrategia reprovada na regra do repo; em avaliacao fora da amostra.</div>',
    ]
    if log.empty or state is None:
        body.append('<div class="card" style="margin-top:16px">Aguardando o primeiro disparo diario do paper.</div>')
    else:
        eq = log["equity"].to_numpy()
        ret = eq[-1] - 1
        dd = float((log["equity"] / log["equity"].cummax() - 1).min())
        last = log.iloc[-1]
        days = len(log)
        kpis = [
            ("Equity", f"{eq[-1]:.4f}".replace(".", ","), _cls(ret)),
            ("Retorno desde o inicio", _pct(ret), _cls(ret)),
            ("Max drawdown", _pct(dd), "neg" if dd < 0 else ""),
            ("Exposicao bruta", f"{last['gross'] * 100:.1f}%".replace(".", ","), ""),
            ("Dias de paper", str(days), ""),
        ]
        body.append('<div class="kpis">' + "".join(
            f'<div class="card"><div class="k">{k}</div><div class="v {c}">{v}</div></div>' for k, v, c in kpis) + "</div>")
        body.append("<h2>Equity</h2><div class=\"card\">" + equity_svg(log) + "</div>")
        body.append(f"<h2>Pesos atuais (fracao do capital, em {last['date']:%d/%m/%Y})</h2><div class=\"card\">"
                    + weights_html(state["weights"]) + "</div>")
        rows = "".join(
            f"<tr><td>{r.date:%d/%m/%Y}</td><td class=\"{_cls(r.pnl)}\">{_pct(r.pnl, 3)}</td>"
            f"<td>{_pct(r.funding, 3)}</td><td>{_pct(r.cost, 3)}</td><td>{r.equity:.4f}</td></tr>".replace("nan", "-")
            for r in log.tail(15).iloc[::-1].itertuples())
        body.append("<h2>Ultimos dias</h2><div class=\"card\"><table><tr><th>Dia</th><th>PnL</th><th>Funding</th>"
                    f"<th>Custo</th><th>Equity</th></tr>{rows}</table></div>")
    body.append("<h2>Estudo</h2><div class=\"card\">" + criteria_html(results_md) + "</div>")
    body.append('<p class="note">Reavaliar com os mesmos criterios apos 12 meses de paper. Nada aqui e recomendacao de '
                "investimento; o paper simula execucao com custo de 7 bps por lado e funding real.</p>")
    return ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta name=\"robots\" content=\"noindex,nofollow\"><title>quant paper</title>"
            f"<style>{CSS}</style></head><body><main>{''.join(body)}</main></body></html>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("QUANT_SITE_DIR", "site"))
    ap.add_argument("--results", default=str(Path(__file__).resolve().parents[2] / "estudos" / "tsmom_cripto" / "reports"
                                              / "resultados.md"))
    a = ap.parse_args()
    state_path = Path(os.environ.get("QUANT_PORT_STATE", "portfolio_state.json"))
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    log = read_log(Path(os.environ.get("QUANT_PORT_LOG", "portfolio_log.csv")))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(build_html(state, log, Path(a.results)), encoding="utf-8")
    print(f"painel gerado em {out / 'index.html'}")


if __name__ == "__main__":
    main()
