import { Component, computed, inject, signal } from '@angular/core';
import { fmt, pct, tone } from '../core/format';
import { StatusStore } from '../core/status.store';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { LineChart } from '../shared/line-chart';
import { PageHead } from '../shared/page-head';

type Filter = 'all' | 'win' | 'loss';

@Component({
  selector: 'app-trades',
  imports: [Kpi, LineChart, PageHead, Icon],
  styles: `.why{min-width:240px;max-width:460px}td:first-child{white-space:nowrap}`,
  template: `
    <app-page-head title="Trades" subtitle="Histórico de posições fechadas pelo runner e PnL acumulado">
      <a class="btn" href="api/trades.csv" download="trades.csv"><app-icon name="download" [size]="16" /> Baixar CSV</a>
    </app-page-head>
    @if (t(); as t) {
      <div class="grid cols-3">
        <app-kpi label="PnL acumulado" [value]="t.count ? fmt(t.pnl_total, 4) : '—'" [tone]="tone(t.pnl_total)"
                 [sub]="t.count ? t.count + ' trade(s) fechado(s)' : 'nenhum trade fechado ainda'" />
        <app-kpi label="taxa de acerto" [value]="t.count ? pct(t.win_rate, 0).replace('+', '') : '—'" [sub]="t.count ? t.wins + ' ganhos · ' + (t.count - t.wins) + ' perdas' : ''" />
        <app-kpi label="pior queda" [value]="t.count ? fmt(t.max_dd, 4) : '—'" [tone]="t.max_dd < 0 ? 'bad' : ''" sub="do pico ao vale da curva" />
      </div>

      <section class="card mt">
        <div class="card-h"><div><h2>PnL acumulado</h2><div class="sub">soma dos trades fechados, em ordem</div></div></div>
        <app-line-chart [values]="curve()" [labels]="curveLabels()" [height]="200" [baseline]="0" [format]="money" label="PnL acumulado"
                        empty="a curva aparece quando houver 2 trades ou mais" />
      </section>

      <section class="card mt">
        <div class="card-h">
          <h2>Últimos trades</h2>
          <div class="seg" role="group" aria-label="filtro">
            <button [class.on]="filter() === 'all'" (click)="filter.set('all')">todos</button>
            <button [class.on]="filter() === 'win'" (click)="filter.set('win')">ganhos</button>
            <button [class.on]="filter() === 'loss'" (click)="filter.set('loss')">perdas</button>
          </div>
        </div>
        @if (rows().length) {
          <div class="scroll-y">
            <table>
              <thead><tr><th>quando</th><th>lado</th><th class="r">entrada</th><th class="r">saída</th><th class="r">PnL</th><th>motivo</th><th>origem</th></tr></thead>
              <tbody>
                @for (x of rows(); track x.ts + x.entrada) {
                  <tr>
                    <td>{{ x.ts.slice(5, 16) }}</td>
                    <td><span class="pill" [class]="x.side > 0 ? 'ok' : 'bad'">{{ x.side > 0 ? 'LONG' : 'SHORT' }}</span></td>
                    <td class="r">{{ fmt(x.entrada) }}</td>
                    <td class="r">{{ fmt(x.saida) }}</td>
                    <td class="r"><b [class]="tone(x.pnl)">{{ fmt(x.pnl, 4) }}</b></td>
                    <td class="why"><span class="clamp" [title]="x.motivo">{{ x.motivo }}</span></td>
                    <td class="sub">{{ x.origem }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <div class="empty"><b>{{ t.count ? 'Nenhum trade neste filtro' : 'Nenhum trade fechado ainda' }}</b>
            {{ t.count ? 'Troque o filtro acima.' : 'O runner grava cada posição fechada aqui, com preço de entrada, saída, PnL e motivo.' }}</div>
        }
        <p class="note mt">O PnL de saída por stop da corretora é uma estimativa: o runner não vê o preço real do fill do gatilho.</p>
      </section>
    } @else {
      <div class="sk" style="height:300px"></div>
    }`,
})
export class TradesPage {
  private readonly store = inject(StatusStore);
  protected readonly filter = signal<Filter>('all');
  protected readonly t = computed(() => this.store.data()?.trades ?? null);
  protected readonly curve = computed(() => (this.t()?.curve ?? []).map(p => p[1]));
  protected readonly curveLabels = computed(() => (this.t()?.curve ?? []).map(p => String(p[0]).slice(5, 16)));
  protected readonly rows = computed(() => {
    const all = this.t()?.trades ?? [];
    const f = this.filter();
    return f === 'all' ? all : all.filter(x => (f === 'win' ? x.pnl > 0 : x.pnl < 0));
  });
  protected readonly money = (v: number) => fmt(v, 4);
  protected readonly fmt = fmt;
  protected readonly pct = pct;
  protected readonly tone = tone;
}
