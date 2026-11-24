import { Component, computed, inject } from '@angular/core';
import { fmt, pct, tone } from '../core/format';
import { StatusStore } from '../core/status.store';
import { LineChart } from '../shared/line-chart';
import { StatCard } from '../shared/stat-card';

@Component({
  selector: 'app-portfolio',
  imports: [StatCard, LineChart],
  styles: `
    .w{display:grid;grid-template-columns:78px 1fr 70px;gap:8px;align-items:center;font-size:13px;padding:2px 0}
    .track{position:relative;height:10px;background:var(--line);border-radius:4px}
    .mid{position:absolute;left:50%;top:-2px;width:1px;height:14px;background:var(--mute)}
    .bar{position:absolute;top:0;height:100%;border-radius:4px}
    .r{text-align:right}`,
  template: `
    <h2>Carteira tsmom_cripto (paper)</h2>
    @if (p(); as p) {
      <div class="grid">
        <app-stat label="equity (base 1,00)" [value]="fmt(p.equity, 4)" [tone]="tone(p.equity, 1)"
                  [sub]="pct((p.equity ?? 1) - 1) + ' desde o início · ' + p.days + ' dia(s) · até ' + p.last_date" />
        <app-stat label="PnL do último dia" [value]="pct(p.pnl, 3)" [tone]="tone(p.pnl)" />
      </div>
      <div class="card mt">
        <app-line-chart [values]="series()" [height]="150" [baseline]="1" label="equity do paper" empty="a curva aparece com 2 dias ou mais" />
        @for (w of weights(); track w.name) {
          <div class="w">
            <span>{{ w.name }}</span>
            <div class="track">
              <div class="mid"></div>
              <div class="bar" [style.width.%]="w.width" [style.left.%]="w.value >= 0 ? 50 : 50 - w.width"
                   [style.background]="w.value >= 0 ? 'var(--ok)' : 'var(--bad)'"></div>
            </div>
            <span class="r">{{ pct(w.value, 1) }}</span>
          </div>
        }
      </div>
      <p class="note">Paper com dados reais. O veredito só vale depois de ~12 meses (regra do repo); a estratégia foi reprovada no estudo e roda só para acumular evidência.</p>
    } @else {
      <div class="card s">sem dados do paper ainda</div>
    }`,
})
export class PortfolioPage {
  private readonly store = inject(StatusStore);
  protected readonly p = computed(() => this.store.data()?.portfolio ?? null);
  protected readonly series = computed(() => (this.p()?.series ?? []).map(s => s[1]).filter((x): x is number => x != null));
  protected readonly weights = computed(() => {
    const w = this.p()?.weights ?? {};
    const names = Object.keys(w);
    const mx = Math.max(0.0001, ...names.map(n => Math.abs(w[n] ?? 0)));
    return names.map(n => ({ name: n.replace('USDT', ''), value: w[n] ?? 0, width: Math.abs(w[n] ?? 0) / mx * 50 }));
  });
  protected readonly fmt = fmt;
  protected readonly pct = pct;
  protected readonly tone = tone;
}
