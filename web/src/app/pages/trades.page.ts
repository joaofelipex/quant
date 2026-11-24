import { Component, computed, inject } from '@angular/core';
import { fmt, pct, tone } from '../core/format';
import { StatusStore } from '../core/status.store';
import { LineChart } from '../shared/line-chart';
import { StatCard } from '../shared/stat-card';

@Component({
  selector: 'app-trades',
  imports: [StatCard, LineChart],
  styles: `
    table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
    th{text-align:left;color:var(--mute);font-weight:500;padding:4px 8px;border-bottom:1px solid var(--line)}
    td{padding:4px 8px;border-bottom:1px solid var(--line)}
    td.r,th.r{text-align:right}
    .scroll{overflow-x:auto}`,
  template: `
    <h2>Histórico de trades e PnL</h2>
    @if (t(); as t) {
      <div class="grid">
        <app-stat label="PnL acumulado" [value]="t.count ? fmt(t.pnl_total, 4) : '—'" [tone]="tone(t.pnl_total)"
                  [sub]="t.count ? t.count + ' trade(s) fechado(s)' : 'nenhum trade fechado ainda'" />
        <app-stat label="acerto" [value]="t.count ? pct(t.win_rate, 0).replace('+', '') : '—'" />
        <app-stat label="pior queda" [value]="t.count ? fmt(t.max_dd, 4) : '—'" [tone]="t.max_dd < 0 ? 'bad' : ''" />
      </div>
      <div class="card mt">
        <app-line-chart [values]="curve()" [height]="140" [baseline]="0" label="PnL acumulado"
                        empty="a curva aparece com 2 trades ou mais" />
        <div class="row mt"><a class="act" href="api/trades.csv" download="trades.csv">Baixar CSV</a></div>
      </div>
      <h2>Últimos trades</h2>
      @if (t.trades.length) {
        <div class="card scroll">
          <table>
            <thead><tr><th>quando</th><th>lado</th><th class="r">entrada</th><th class="r">saída</th><th class="r">PnL</th><th>motivo</th><th>origem</th></tr></thead>
            <tbody>
              @for (x of t.trades; track x.ts + x.entrada) {
                <tr>
                  <td>{{ x.ts.slice(5, 16) }}</td>
                  <td>{{ x.side > 0 ? 'long' : 'short' }}</td>
                  <td class="r">{{ fmt(x.entrada) }}</td>
                  <td class="r">{{ fmt(x.saida) }}</td>
                  <td class="r" [class]="tone(x.pnl)">{{ fmt(x.pnl, 4) }}</td>
                  <td>{{ x.motivo }}</td>
                  <td class="s">{{ x.origem }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <div class="card s">sem trades ainda</div>
      }
      <p class="note">O PnL de saída por stop da corretora é uma estimativa: o runner não vê o preço real do fill do gatilho.</p>
    }`,
})
export class TradesPage {
  private readonly store = inject(StatusStore);
  protected readonly t = computed(() => this.store.data()?.trades ?? null);
  protected readonly curve = computed(() => (this.t()?.curve ?? []).map(p => p[1]));
  protected readonly fmt = fmt;
  protected readonly pct = pct;
  protected readonly tone = tone;
}
