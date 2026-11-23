"""Estudo funding_carry: carry de funding delta-neutro (spot comprado + perpetuo vendido) em cripto.

    for s in BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT; do
        python -m quant.data.fetch_binance $s 1d 2020-01 2025-10          # spot
        python -m quant.data.fetch_binance $s 1d 2020-01 2025-10 --perp   # perpetuo
        python -m quant.data.fetch_funding $s 2020-01 2025-10
    done
    python estudos/funding_carry/run_study.py

Desenho PRE-REGISTRADO (fixado antes de calcular qualquer retorno da estrategia; nada foi reotimizado):
* universo primario: BTC e ETH (os mais liquidos; capital dividido em partes iguais). Os 6 pares entram so como
  robustez, NAO no veredito (o universo de 6 foi escolhido em 2025 = vies de sobrevivencia).
* sinal: funding medio dos ultimos L dias (ate ontem), anualizado, acima de um piso H -> liga a posicao.
  Variante primaria L=14, H=5% a.a. Grade olhada: L em (7, 14, 30) x H em (0%, 5%, 10%) + sempre ligado = 10 variantes
  x 2 universos => N_TRIALS = 20 (usado no DSR).
* custo: 20 bps por troca de estado (abrir ou fechar as DUAS pernas: taxas spot ~10 bps + perp ~5 bps + slippage);
  margem do perpetuo = 20% do nocional, capital parado que rende zero; margem recomposta todo dia.
* periodos: dev 2020-01-01 a 2023-06-30; hold-out de 2023-07-01 em diante, so no veredito.
* criterios de aprovacao (todos): (1) retorno liquido anual no hold-out > 4% (juro USD de referencia); (2) DSR >= 0,95;
  (3) retorno anual > 0 com custos x3 no hold-out; (4) bootstrap em blocos: P(retorno medio <= 0) < 5% no hold-out;
  (5) nenhum dia de risco de liquidacao com a posicao ligada (periodo todo) e drawdown maximo do hold-out >= -5%.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from quant.metrics import sharpe  # noqa: E402
from quant.strategies import funding_carry as fc  # noqa: E402
from quant.validation import block_bootstrap_mean, deflated_sharpe_ratio  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "dados" / "raw" / "binance"
REPORTS = Path(__file__).resolve().parent / "reports"

ALL = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
PRIMARY_UNIVERSE = ["BTCUSDT", "ETHUSDT"]
HOLDOUT_START = "2023-07-01"
MARGIN, SWITCH_COST_BPS, USD_HURDLE = 0.20, 20.0, 0.04
LOOKBACKS, HURDLES = (7, 14, 30), (0.0, 0.05, 0.10)
PRIMARY = (14, 0.05)
N_TRIALS = 20
PPY = fc.DAYS_PER_YEAR


def load_panel(symbols):
    so, po, ph, sh, fd = {}, {}, {}, {}, {}
    for s in symbols:
        sp = pd.read_csv(RAW / f"{s}_1d.csv", parse_dates=["datetime"])
        pp = pd.read_csv(RAW / f"{s}_1d_perp.csv", parse_dates=["datetime"])
        for d in (sp, pp):
            d["datetime"] = d["datetime"].dt.tz_localize(None).dt.normalize()
        so[s] = sp.set_index("datetime")["open"]
        sh[s] = sp.set_index("datetime")["high"]
        po[s] = pp.set_index("datetime")["open"]
        ph[s] = pp.set_index("datetime")["high"]
        fd[s] = fc.daily_funding(pd.read_csv(RAW / f"{s}_funding.csv", parse_dates=["datetime"]))
    idx = pd.DataFrame(so).index
    return {"so": pd.DataFrame(so), "po": pd.DataFrame(po).reindex(idx), "ph": pd.DataFrame(ph).reindex(idx),
            "sh": pd.DataFrame(sh).reindex(idx), "fd": pd.DataFrame(fd).reindex(idx)}


def run(panel, universe, lookback, hurdle, cost_x=1.0, margin=MARGIN):
    so, po, ph, fd = (panel[k][universe] for k in ("so", "po", "ph", "fd"))
    avail = so.notna() & po.notna() & fd.notna()
    on = (pd.DataFrame(True, index=so.index, columns=so.columns) if lookback is None
          else fc.carry_signal(fd, lookback, hurdle)) & avail
    res = fc.carry_returns(so, po, fd, on, SWITCH_COST_BPS * cost_x, margin)
    port = fc.portfolio(res)
    return port, res, on, fc.liquidation_days(po, ph, on, margin)


def sl(s, a, b=None):
    return s[(s.index >= a) & ((s.index < b) if b else True)]


def stats(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    return {"ret_anual": float(r.mean() * PPY), "vol": float(r.std() * np.sqrt(PPY)), "sharpe": sharpe(r, PPY),
            "max_dd": float((eq / eq.cummax() - 1).min()), "pior_30d": float(r.rolling(30).sum().min())}


def fmt(df: pd.DataFrame, nd=3) -> str:
    return "```\n" + df.round(nd).to_string() + "\n```"


def main() -> None:
    universe_all = [s for s in ALL if (RAW / f"{s}_1d_perp.csv").exists()]  # robustez usa so os pares baixados
    panel = load_panel(universe_all)
    periods = {"dev": (None, HOLDOUT_START), "holdout": (HOLDOUT_START, None), "total": (None, None)}

    def cut(s, a, b):
        return sl(s, a or "1900-01-01", b)

    # ---- 1. grade de variantes (robustez, nao selecao) ------------------------------------------------------
    rows = []
    for uname, uni in (("BTC+ETH", PRIMARY_UNIVERSE), (f"{len(universe_all)} pares", universe_all)):
        for lb, h in [(None, None)] + [(lb, h) for lb in LOOKBACKS for h in HURDLES]:
            port, *_ = run(panel, uni, lb, h)
            name = "sempre_ligado" if lb is None else f"L{lb}_H{h:.0%}"
            rows.append({"universo": uname, "variante": name,
                         **{f"ret_{p}": cut(port["net"], *periods[p]).mean() * PPY for p in periods},
                         "sharpe_holdout": sharpe(cut(port["net"], *periods["holdout"]), PPY)})
    grid = pd.DataFrame(rows).set_index(["universo", "variante"])

    # ---- 2. variante primaria ------------------------------------------------------------------------------------
    port, res, on, liq = run(panel, PRIMARY_UNIVERSE, *PRIMARY)
    perf = {}
    for pname, (a, b) in periods.items():
        r = cut(port["net"], a, b)
        perf[pname] = {**stats(r),
                       "funding_ano": float(cut(port["funding"], a, b).mean() * PPY),
                       "base_ano": float(cut(port["basis"], a, b).mean() * PPY),
                       "custo_ano": float(cut(port["cost"], a, b).mean() * PPY),
                       "tempo_ligado": float(cut(on.mean(axis=1), a, b).mean())}
    always, *_ = run(panel, PRIMARY_UNIVERSE, None, None)
    for pname, (a, b) in periods.items():
        perf[f"sempre_ligado_{pname}"] = stats(cut(always["net"], a, b))
    perf_df = pd.DataFrame(perf).T

    ho = cut(port["net"], *periods["holdout"])
    dsr = deflated_sharpe_ratio(ho, N_TRIALS)
    boot = block_bootstrap_mean(ho)
    stress = pd.DataFrame({f"custo_x{f:g}": {
        "ret_anual_holdout": cut(run(panel, PRIMARY_UNIVERSE, *PRIMARY, cost_x=f)[0]["net"], *periods["holdout"]).mean()
        * PPY} for f in (0, 1, 2, 3, 5)}).T

    # por ano e por ativo (primaria)
    yearly = pd.DataFrame({
        "ret_liquido": port["net"].groupby(port.index.year).sum(),
        "funding": port["funding"].groupby(port.index.year).sum(),
        "base": port["basis"].groupby(port.index.year).sum(),
        "custo": port["cost"].groupby(port.index.year).sum(),
        "tempo_ligado": on.mean(axis=1).groupby(on.index.year).mean(),
        "funding_bruto_btc_eth_aa":
            panel["fd"][PRIMARY_UNIVERSE].mean(axis=1).groupby(panel["fd"].index.year).mean() * PPY,
    }).dropna(how="all")
    by_asset = pd.DataFrame({s.replace("USDT", ""): stats(cut(res["net"][s], *periods["holdout"]))
                             for s in PRIMARY_UNIVERSE}).T[["ret_anual", "sharpe", "max_dd"]]
    n_liq = int(liq.sum().sum())
    spike_perp = panel["ph"][PRIMARY_UNIVERSE] / panel["po"][PRIMARY_UNIVERSE] - 1
    spike_spot = panel["sh"][PRIMARY_UNIVERSE] / panel["so"][PRIMARY_UNIVERSE] - 1  # proxy do preco de marcacao
    thr = MARGIN - 0.005
    n_liq_spot = int(((spike_spot >= thr) & on).sum().sum())
    events = pd.concat({s.replace("USDT", ""): pd.DataFrame({
        "alta_perp": spike_perp[s], "alta_spot": spike_spot[s], "ligado": on[s]})[
        ((spike_perp[s] >= thr) | (spike_spot[s] >= thr))] for s in PRIMARY_UNIVERSE})
    events.index = events.index.set_names(["ativo", "dia"])
    max_spike_spot = float(spike_spot[on].max().max())
    gap = events["alta_perp"] - events["alta_spot"]
    worst_day = f"{gap.idxmax()[0]} {gap.idxmax()[1]:%Y-%m-%d}"
    worst_perp, worst_spot = float(events.loc[gap.idxmax(), "alta_perp"]), float(events.loc[gap.idxmax(), "alta_spot"])

    def margin_row(m):
        pm, _, _, lm = run(panel, PRIMARY_UNIVERSE, *PRIMARY, margin=m)
        return {"ret_anual_holdout": cut(pm["net"], *periods["holdout"]).mean() * PPY,
                "dias_liq_perp": int(lm.sum().sum()),
                "dias_liq_proxy_spot": int(((spike_spot >= m - 0.005) & on).sum().sum())}

    margins = pd.DataFrame({f"margem_{m:.0%}": margin_row(m) for m in (0.20, 0.35, 0.50)}).T

    # ---- 3. veredito -----------------------------------------------------------------------------------------------
    checks = {
        f"1. Retorno liquido anual no hold-out > {USD_HURDLE:.0%}": perf["holdout"]["ret_anual"] > USD_HURDLE,
        f"2. DSR >= 0,95 (N_TRIALS={N_TRIALS})": dsr >= 0.95,
        "3. Retorno anual > 0 com custos x3 (hold-out)": stress.loc["custo_x3", "ret_anual_holdout"] > 0,
        "4. Bootstrap em blocos: P(retorno medio <= 0) < 5% (hold-out)": boot["prob_le_0"] < 0.05,
        "5. Zero dias de liquidacao com a posicao ligada e drawdown do hold-out >= -5%":
            n_liq == 0 and perf["holdout"]["max_dd"] >= -0.05,
    }
    verdict = "APROVADA" if all(checks.values()) else "REPROVADA"

    REPORTS.mkdir(exist_ok=True)
    out = f"""# funding_carry - resultados

Periodo: {panel["so"].index.min():%Y-%m-%d} a {panel["so"].index.max():%Y-%m-%d}. Hold-out a partir de {HOLDOUT_START}.
Primaria: BTC+ETH, L={PRIMARY[0]} dias, piso {PRIMARY[1]:.0%} a.a.
Custo {SWITCH_COST_BPS:g} bps/troca, margem {MARGIN:.0%}.
Retornos SOBRE O CAPITAL (nocional x (1 + margem)); caixa e margem rendem zero.

## Veredito: **{verdict}**
""" + "\n".join(f"- [{'x' if v else ' '}] {k}" for k, v in checks.items()) + f"""

## Desempenho da variante primaria (liquido de custos)
{fmt(perf_df)}

DSR (hold-out, N_TRIALS={N_TRIALS}): {dsr:.3f}. Bootstrap em blocos da media diaria (hold-out): IC 90% de retorno
anual [{boot['mean_p5'] * PPY:.1%}, {boot['mean_p95'] * PPY:.1%}], P(media <= 0) = {boot['prob_le_0']:.1%}.

## Risco de cauda (BTC+ETH): a perna vendida do perpetuo pode ser liquidada
Criterio pre-registrado (alta do perpetuo, high/abertura, >= margem livre de {thr:.1%}): **{n_liq} dias com a posicao
ligada**. Pela maxima do SPOT (proxy do preco de marcacao, que e o que a corretora usa para liquidar): **{n_liq_spot}
dias com a posicao ligada**, ou seja, altas reais de 20% ou mais em 24 h. A maxima do perpetuo tem tambem mechas
anomalas: a pior foi {worst_day} (+{worst_perp:.0%} no perpetuo contra +{worst_spot:.0%} no spot).
Maior alta do spot com a posicao ligada: {max_spike_spot:.1%}.

{fmt(events)}

Margem maior evita a liquidacao mas dilui o retorno (mais capital parado):
{fmt(margins, 4)}
Nao modelado: margem unificada/portfolio margin (o spot como colateral reduziria o risco) e recomposicao intradiaria.

## Estresse de custos (primaria, retorno anual do hold-out)
{fmt(stress, 4)}

## Por ano (primaria; soma dos retornos diarios sobre o capital)
{fmt(yearly)}

## Por ativo (hold-out)
{fmt(by_asset)}

## Grade de variantes (retorno anual liquido; robustez, nao selecao)
{fmt(grid)}
"""
    (REPORTS / "resultados.md").write_text(out, encoding="utf-8")
    print(out)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name, r in (("carry primaria (L14, H5%)", port["net"]), ("sempre ligado", always["net"])):
        ax.plot(r.index, (1 + r).cumprod(), label=name)
    ax.axvline(pd.Timestamp(HOLDOUT_START), color="k", ls="--", lw=0.8, label="inicio do hold-out")
    ax.set_title("funding_carry BTC+ETH - equity sobre o capital, liquida de custos")
    ax.legend()
    fig.savefig(REPORTS / "equity.png", dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()
