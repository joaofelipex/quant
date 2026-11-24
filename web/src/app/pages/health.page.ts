import { Component, computed, inject, signal } from '@angular/core';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { runAction } from '../core/action';
import { filterLog, fmt, logTone, LogFilter, pct, tone } from '../core/format';
import { StatusStore } from '../core/status.store';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

@Component({
  selector: 'app-health',
  imports: [Kpi, PageHead, Icon],
  styles: `
    .seg{display:inline-flex;border:1px solid var(--line-strong);border-radius:10px;overflow:hidden}
    .seg button{font:inherit;font-size:13px;font-weight:600;padding:6px 13px;border:none;background:transparent;color:var(--mute);cursor:pointer}
    .seg button.on{background:var(--accent-soft);color:var(--accent)}
    .chk{display:flex;align-items:center;gap:10px}
    .chk app-icon{flex:none}`,
  template: `
    <app-page-head title="Saúde" subtitle="Testes automáticos da VM, serviços e log do runner">
      <button class="btn" [disabled]="!auth.canOperate() || busy()" (click)="run()"><app-icon name="refresh" [size]="16" /> Rodar agora</button>
    </app-page-head>

    @if (sc(); as sc) {
      <div class="grid cols-3">
        <app-kpi label="última verificação" [value]="sc.ok ? 'tudo certo' : 'FALHOU'" [tone]="sc.ok ? 'ok' : 'bad'" [sub]="when(sc.at)" />
        @if (sc.tests; as t) {
          <app-kpi label="suite pytest" [value]="t.passed + ' ok'" [tone]="t.ok ? 'ok' : 'bad'"
                   [sub]="t.failed + ' falhas · ' + t.skipped + ' ignorados · ' + t.seconds + ' s' + (t.failures.length ? ' · ' + t.failures.join(', ') : '')" />
        }
        @if (sc.paper; as p) {
          <app-kpi label="paper da carteira" [value]="p.sharpe == null ? 'sem Sharpe' : 'Sharpe ' + fmt(p.sharpe)" [tone]="tone(p.sharpe)"
                   [sub]="p.days + ' dia(s) · ret ' + pct(p.ret_total) + ' · ' + p.verdict" />
        }
      </div>
      <section class="card mt">
        <div class="card-h"><h2>Checagens dos serviços</h2></div>
        <div class="list">
          @for (c of sc.checks; track c.name) {
            <div class="chk"><app-icon [name]="c.ok ? 'check' : 'alert'" [size]="17" [class]="c.ok ? 'ok' : 'bad'" /><span>{{ c.name }}</span><span class="sub" style="margin-left:auto">{{ c.detail }}</span></div>
          }
        </div>
      </section>
    } @else {
      <div class="card"><div class="empty"><b>Sem relatório ainda</b>A primeira verificação roda sozinha; ou clique em "Rodar agora".</div></div>
    }
    <p class="note mt">Roda sozinha a cada 6 h: pytest, saúde dos serviços e avaliação do paper. Só lê e testa; não altera serviços nem usa chaves.
      O veredito do paper só vale depois de ~12 meses (regra do repo).</p>

    <section class="card mt">
      <div class="card-h">
        <h2>Log do runner</h2>
        <div class="seg" role="group" aria-label="filtro do log">
          <button [class.on]="filter() === 'all'" (click)="filter.set('all')">tudo</button>
          <button [class.on]="filter() === 'key'" (click)="filter.set('key')">ordens e avisos</button>
          <button [class.on]="filter() === 'err'" (click)="filter.set('err')">só erros</button>
        </div>
      </div>
      <pre class="log">@for (l of lines(); track $index) {<span class="l" [class]="logTone(l)">{{ l }}</span>} @empty {(sem linhas para este filtro)}</pre>
    </section>`,
})
export class HealthPage {
  private readonly store = inject(StatusStore);
  protected readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  protected readonly sc = computed(() => this.store.data()?.selfcheck ?? null);
  protected readonly filter = signal<LogFilter>('all');
  protected readonly lines = computed(() => filterLog(this.store.data()?.log ?? [], this.filter()));
  protected readonly busy = signal(false);
  protected readonly fmt = fmt;
  protected readonly pct = pct;
  protected readonly tone = tone;
  protected readonly logTone = logTone;
  protected when = (iso: string) => new Date(iso).toLocaleString('pt-BR');

  protected run(): void {
    this.busy.set(true);
    runAction(this.toast, this.api.runSelfcheck(), () => 'Verificação em execução; o resultado aparece em ~1 min',
              () => { this.busy.set(false); this.store.refresh(); });
  }
}
