import { Component, computed, inject, signal } from '@angular/core';
import { ApiService, errMsg } from '../core/api.service';
import { Study } from '../core/models';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { PageHead } from '../shared/page-head';

@Component({
  selector: 'app-research',
  imports: [Kpi, PageHead, Icon],
  template: `
    <app-page-head title="Pesquisa" subtitle="O que já foi testado, com que resultado. Fonte: tabela de estudos do repositório">
      <input type="search" placeholder="buscar: cripto, momentum, fluxo…" aria-label="buscar estudo" style="width:260px"
             [value]="query()" (input)="query.set($any($event.target).value)" />
    </app-page-head>

    @if (error()) { <div class="alert bad" role="alert"><app-icon name="alert" [size]="18" /> <span>Não consegui ler os estudos: {{ error() }}</span></div> }

    <div class="grid cols-3">
      <app-kpi label="estudos registrados" [value]="'' + studies().length" />
      <app-kpi label="reprovados ou sem vantagem" [value]="'' + failed()" tone="bad" />
      <app-kpi label="liberados para conta real" value="0" sub="regra do repositório" />
    </div>

    <div class="seg mt" role="group" aria-label="situação">
      @for (o of kinds; track o.id) { <button [class.on]="kind() === o.id" (click)="kind.set(o.id)">{{ o.label }}</button> }
    </div>

    <div class="grid cols-2 mt">
      @for (s of shown(); track s.nome) {
        <section class="card">
          <div class="card-h"><h2 class="mono">{{ s.nome }}</h2><span class="pill" [class]="s.tom">{{ s.status }}</span></div>
          <p>{{ s.hipotese }}</p>
          <p class="sub mt"><b>Resultado:</b> {{ s.resultado }}</p>
        </section>
      } @empty { <div class="card"><div class="empty">{{ studies().length ? 'nenhum estudo com esse filtro' : 'carregando…' }}</div></div> }
    </div>`,
})
export class ResearchPage {
  protected readonly studies = signal<Study[]>([]);
  protected readonly query = signal('');
  protected readonly kinds = [{ id: '', label: 'todos' }, { id: 'bad', label: 'reprovados ou sem vantagem' }, { id: 'warn', label: 'em aberto' }];
  protected readonly kind = signal('');
  protected readonly error = signal<string | null>(null);
  protected readonly failed = computed(() => this.studies().filter(s => s.tom === 'bad').length);
  protected readonly shown = computed(() => {
    const q = this.query().trim().toLowerCase(), k = this.kind();
    return this.studies().filter(s => (!k || s.tom === k)
      && (!q || `${s.nome} ${s.hipotese} ${s.resultado} ${s.status}`.toLowerCase().includes(q)));
  });

  constructor() {
    inject(ApiService).research().subscribe({ next: r => this.studies.set(r.estudos), error: e => this.error.set(errMsg(e)) });
  }
}
