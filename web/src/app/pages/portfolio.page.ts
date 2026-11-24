import { Component, computed, inject } from '@angular/core';
import { fmt, pct, tone } from '../core/format';
import { StatusStore } from '../core/status.store';
import { Kpi } from '../shared/kpi';
import { LineChart } from '../shared/line-chart';
import { PageHead } from '../shared/page-head';

@Component({
  selector: 'app-portfolio',
  imports: [Kpi, LineChart, PageHead],
  styles: `
    .w{display:grid;grid-template-columns:64px 1fr 64px;gap:12px;align-items:center;font-size:13.5px;padding:5px 0}
    .track{position:relative;height:10px;background:var(--surface-2);border:1px solid var(--line);border-radius:6px}
    .mid{position:absolute;left:50%;top:-3px;width:1px;height:14px;background:var(--faint)}
    .bar{position:absolute;top:0;height:100%;border-radius:5px}`,
  template: `
    <app-page-head title="Carteira" subtitle="tsmom_cripto em paper (dados reais, sem ordens): equity e pesos do último dia" />
    @if (p(); as p) {
      <div class="grid cols-3">
        <app-kpi label="equity (base 1,00)" [value]="fmt(p.equity, 4)" [tone]="tone(p.equity, 1)"
                 [sub]="pct((p.equity ?? 1) - 1) + ' desde o início'" />
        <app-kpi label="PnL do último dia" [value]="pct(p.pnl, 3)" [tone]="tone(p.pnl)" [sub]="'até ' + p.last_date" />
        <app-kpi label="dias de paper" [value]="'' + p.days" sub="o veredito só vale após ~12 meses" />
      </div>
      <section class="card mt">
        <div class="card-h"><h2>Curva de equity</h2></div>
        <app-line-chart [values]="series()" [labels]="dates()" [height]="200" [baseline]="1" [format]="eq" label="equity do paper"
                        empty="a curva aparece quando houver 2 dias ou mais" />
      </section>
      <section class="card mt">
        <div class="card-h"><div><h2>Pesos do último dia</h2><div class="sub">verde = comprado, vermelho = vendido</div></div></div>
        @for (w of weights(); track w.name) {
          <div class="w">
            <b>{{ w.name }}</b>
            <div class="track">
              <div class="mid"></div>
              <div class="bar" [style.width.%]="w.width" [style.left.%]="w.value >= 0 ? 50 : 50 - w.width"
                   [style.background]="w.value >= 0 ? 'var(--ok)' : 'var(--bad)'"></div>
            </div>
            <span class="num r">{{ pct(w.value, 1) }}</span>
          </div>
        }
      </section>
      <p class="note mt">Esta estratégia foi <b>reprovada</b> no estudo (README do repo) e roda só para acumular evidência em tempo real.</p>
    } @else {
      <div class="card"><div class="empty"><b>Sem dados do paper ainda</b>O timer diário grava o primeiro dia à meia-noite UTC.</div></div>
    }`,
})
export class PortfolioPage {
  private readonly store = inject(StatusStore);
  protected readonly p = computed(() => this.store.data()?.portfolio ?? null);
  private readonly pts = computed(() => (this.p()?.series ?? []).filter((s): s is [string, number] => s[1] != null));
  protected readonly series = computed(() => this.pts().map(s => s[1]));
  protected readonly dates = computed(() => this.pts().map(s => s[0]));
  protected readonly weights = computed(() => {
    const w = this.p()?.weights ?? {};
    const names = Object.keys(w);
    const mx = Math.max(0.0001, ...names.map(n => Math.abs(w[n] ?? 0)));
    return names.map(n => ({ name: n.replace('USDT', ''), value: w[n] ?? 0, width: Math.abs(w[n] ?? 0) / mx * 50 }));
  });
  protected readonly eq = (v: number) => fmt(v, 4);
  protected readonly fmt = fmt;
  protected readonly pct = pct;
  protected readonly tone = tone;
}
