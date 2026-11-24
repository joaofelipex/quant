import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { Msg, NO_MSG, runAction } from '../core/action';
import { filterLog, fmt, logTone, LogFilter, pct } from '../core/format';
import { StatusStore } from '../core/status.store';
import { StatCard } from '../shared/stat-card';

@Component({
  selector: 'app-health',
  imports: [StatCard, FormsModule],
  styles: `
    .l{display:block}
    .bad{color:var(--bad)}.warn{color:var(--warn)}
    .chk{font-size:12px}`,
  template: `
    <h2>Testes automáticos da VM</h2>
    @if (sc(); as sc) {
      <div class="grid">
        <app-stat label="última verificação" [value]="sc.ok ? 'tudo certo' : 'FALHOU'" [tone]="sc.ok ? 'ok' : 'bad'"
                  [sub]="when(sc.at)" />
        @if (sc.tests; as t) {
          <app-stat label="suite pytest" [value]="t.passed + ' ok · ' + t.failed + ' falhas'" [tone]="t.ok ? 'ok' : 'bad'"
                    [sub]="t.seconds + ' s' + (t.failures.length ? ' · ' + t.failures.join(', ') : '')" />
        }
        @if (sc.paper; as p) {
          <app-stat label="paper da carteira" [value]="p.sharpe == null ? 'sem Sharpe' : 'Sharpe ' + fmt(p.sharpe)"
                    [tone]="(p.sharpe ?? 0) > 0 ? 'ok' : ''"
                    [sub]="p.days + ' dia(s) · ret ' + pct(p.ret_total) + ' · DD ' + pct(p.max_dd) + ' · ' + p.verdict" />
        }
      </div>
      <div class="card mt">
        @for (c of sc.checks; track c.name) {
          <div class="chk"><span [class]="c.ok ? 'ok' : 'bad'">{{ c.ok ? '✔' : '✘' }} {{ c.name }}</span> <span class="s">{{ c.detail }}</span></div>
        }
      </div>
    } @else {
      <div class="card s">sem relatório; aguardando a primeira execução</div>
    }
    <div class="row mt">
      <button class="act" (click)="run()">Rodar agora</button>
      <span class="sub" [class]="msg().tone">{{ msg().text }}</span>
    </div>
    <p class="note">Roda sozinha a cada 6 h: pytest, saúde dos serviços e avaliação do paper. Só lê e testa; não altera serviços nem usa chaves.
      O veredito do paper só vale depois de ~12 meses (regra do repo).</p>

    <h2>Log do runner</h2>
    <div class="row">
      <label class="sub">mostrar
        <select [ngModel]="filter()" (ngModelChange)="filter.set($event)">
          <option value="all">tudo</option>
          <option value="key">ordens, avisos e erros</option>
          <option value="err">só avisos e erros</option>
        </select>
      </label>
    </div>
    <pre>@for (l of lines(); track $index) {<span class="l" [class]="logTone(l)">{{ l }}</span>} @empty {(sem linhas para este filtro)}</pre>`,
})
export class HealthPage {
  private readonly store = inject(StatusStore);
  private readonly api = inject(ApiService);
  protected readonly sc = computed(() => this.store.data()?.selfcheck ?? null);
  protected readonly filter = signal<LogFilter>('all');
  protected readonly lines = computed(() => filterLog(this.store.data()?.log ?? [], this.filter()));
  protected readonly msg = signal<Msg>(NO_MSG);
  protected readonly fmt = fmt;
  protected readonly pct = pct;
  protected readonly logTone = logTone;
  protected when = (iso: string) => new Date(iso).toLocaleString('pt-BR');

  protected run(): void {
    runAction(this.msg, this.api.runSelfcheck(), () => 'em execução; atualiza em ~1 min', () => this.store.refresh());
  }
}
