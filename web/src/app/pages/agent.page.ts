import { DatePipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { timer } from 'rxjs';
import { ApiService, errMsg } from '../core/api.service';
import { AgentConfig, AgentDecision, AgentStatus } from '../core/models';
import { AuthService } from '../core/auth.service';
import { fmt, tone } from '../core/format';
import { ConfirmService } from '../shared/confirm';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

const NO_CONFIG: AgentConfig = {
  enabled: false, model: '', interval_min: 10, max_usd: 15, max_positions: 5, max_daily_loss: 2, long_only: true, stop_min: 0.5,
  stop_max: 5, cooldown_min: 20, max_actions: 3, max_hold_h: 24, candidates: 12, universe: 'tudo', edge_min: 2,
  shadow: false,
};

const FIELDS: { key: string; label: string; hint: string }[] = [
  { key: 'max_usd', label: 'Valor máx. por entrada (USD)', hint: 'o código corta qualquer pedido acima disto' },
  { key: 'max_positions', label: 'Posições abertas ao mesmo tempo', hint: 'a IA não abre além disso' },
  { key: 'max_daily_loss', label: 'Perda máxima por dia (USD)', hint: 'ao atingir, ela para de abrir e se desliga' },
  { key: 'stop_min', label: 'Stop mínimo (%)', hint: 'stop é obrigatório em toda entrada' },
  { key: 'stop_max', label: 'Stop máximo (%)', hint: '' },
  { key: 'interval_min', label: 'Intervalo entre ciclos (min)', hint: 'cada ciclo é uma chamada ao modelo (custo)' },
  { key: 'cooldown_min', label: 'Espera após fechar um ativo (min)', hint: 'evita reabrir o mesmo ativo em seguida' },
  { key: 'max_hold_h', label: 'Tempo máximo de posição (h)', hint: 'fecha sozinha ao passar disto' },
  { key: 'edge_min', label: 'Alvo mínimo (x o custo)', hint: 'ganho esperado precisa cobrir N vezes taxas + spread; 0 desliga' },
];

@Component({
  selector: 'app-agent',
  imports: [FormsModule, PageHead, Icon, Kpi, DatePipe],
  template: `
    <app-page-head title="IA" subtitle="Um agente (Claude) que decide e opera na VM, só na conta demo e dentro dos limites abaixo">
      <button class="btn" [disabled]="busy() || !auth.canOperate() || !s()?.chave" (click)="runNow()"><app-icon name="refresh" [size]="15" /> Rodar um ciclo agora</button>
      @if (cfg().enabled) {
        <button class="btn danger" [disabled]="busy() || !auth.canOperate()" (click)="toggle(false)"><app-icon name="stop" [size]="15" /> Desligar</button>
      } @else {
        <button class="btn primary" [disabled]="busy() || !auth.canOperate() || !s()?.chave" (click)="turnOn()"><app-icon name="play" [size]="15" /> Ligar a IA</button>
      }
    </app-page-head>

    @if (s(); as st) {
      @if (!st.chave) {
        <section class="card lock mb-3 flex gap-3 border-[var(--warn)]">
          <app-icon name="alert" />
          <div><b>A chave da IA ainda não foi gravada na VM.</b>
            <p class="note">Rode, num terminal seu, <code>sudo bash /opt/quant/deploy/definir-chave-ia.sh</code> e cole a chave da API da Anthropic, ou, para usar a CLI do Claude com a sua conta, <code>sudo bash /opt/quant/deploy/login-claude-cli.sh</code>
              (ela não aparece na tela e o painel nunca a lê). Sem ela o agente não liga.</p></div>
        </section>
      }
      @if (st.state.last_error) {
        <section class="card mb-3 flex gap-3"><app-icon name="alert" /><div><b class="bad">Último aviso</b><p class="note">{{ st.state.last_error }}</p></div></section>
      }

      <div class="grid cols-4">
        <app-kpi label="estado" [value]="cfg().enabled ? 'ligada' : 'desligada'" [tone]="cfg().enabled ? 'ok' : ''" [sub]="cfg().enabled ? 'a cada ' + cfg().interval_min + ' min' : 'não opera'" />
        <app-kpi label="PnL da IA hoje" [value]="fmt(st.pnl_hoje, 4)" [tone]="tone(st.pnl_hoje)" [sub]="'limite −' + cfg().max_daily_loss + ' USD'" />
        <app-kpi label="posições da IA" [value]="'' + livro().length" [sub]="'máx ' + cfg().max_positions" />
        <app-kpi label="ciclos / tokens" [value]="'' + (st.state.ciclos || 0)" [sub]="(st.state.tokens || 0) + ' tokens · ' + cfg().model" />
      </div>

      <section class="card mt">
        <div class="card-h"><div><h2>Posições abertas pela IA</h2><div class="sub">o stop de cada uma está na corretora, mesmo se a IA ou a VM parar</div></div></div>
        @if (livro().length) {
          <div class="list">
            @for (p of livro(); track p.ativo) {
              <div class="spread">
                <div><b>{{ p.ativo }}</b> <span class="pill" [class]="p.side > 0 ? 'ok' : 'bad'">{{ p.side > 0 ? 'COMPRADO' : 'VENDIDO' }}</span>
                  <span class="sub"> · ~{{ p.usd }} USD · aberta {{ p.opened_at * 1000 | date: 'dd/MM HH:mm' }}</span></div>
                <span class="sub">{{ p.reason }}</span>
              </div>
            }
          </div>
        } @else { <div class="empty"><b>Nenhuma posição</b>A IA só abre quando vê vantagem depois do custo: ficar parada é normal.</div> }
      </section>

      <section class="card mt">
        <div class="card-h"><div><h2>Decisões recentes</h2><div class="sub">cada ciclo guarda o que a IA viu, o que pediu e o que o código aceitou ou recusou</div></div>
          <button class="btn ghost sm" (click)="load()"><app-icon name="refresh" [size]="14" /> atualizar</button></div>
        @for (d of st.decisoes; track d.t) {
          <article class="border-t border-line py-3 first:border-t-0 first:pt-0">
            <div class="spread"><b class="num">{{ d.t * 1000 | date: 'dd/MM HH:mm:ss' }}</b>
              <span class="sub">{{ d.universo }} ativos · {{ d.fotos }} fotos · PnL dia {{ fmt(d.pnl_dia, 4) }}{{ d.uso?.input_tokens ? ' · ' + d.uso.input_tokens + '+' + d.uso.output_tokens + ' tokens' : '' }}</span></div>
            @if (d.erro) { <p class="note bad">{{ d.erro }}</p> }
            @if (d.analise) { <p class="mt-1 text-[14px]">{{ d.analise }}</p> }
            @for (a of d.acoes; track $index) {
              <div class="mt-1.5 flex flex-wrap items-center gap-2 text-[13px]">
                <span class="pill" [class]="pill(a.status)">{{ a.status }}</span>
                <b>{{ a.acao }} {{ a.ativo }}</b>
                @if (a.acao === 'abrir') { <span class="sub">{{ a.usd }} USD · stop {{ a.stop_pct }}%{{ a.ajustado ? ' (valor cortado no limite)' : '' }}</span> }
                <span class="sub">{{ a.motivo }}</span>
                @if (a.why) { <span class="bad">↳ {{ a.why }}</span> }
                @if (a.detalhe) { <span class="sub">↳ {{ a.detalhe }}</span> }
                @if (a.aviso) { <span class="warn">⚠ {{ a.aviso }}{{ a.fechada_por_seguranca ? ' (fechada por segurança)' : '' }}</span> }
              </div>
            } @empty { <p class="sub mt-1">sem ação neste ciclo</p> }
          </article>
        } @empty { <div class="empty"><b>Sem decisões ainda</b>Ligue a IA ou rode um ciclo agora.</div> }
      </section>

      <section class="card mt">
        <div class="card-h"><div><h2>Limites (travas no código)</h2><div class="sub">o modelo pode pedir qualquer coisa; só passa o que cabe aqui. {{ auth.isAdmin() ? '' : 'Só administrador altera.' }}</div></div></div>
        <div class="grid cols-4">
          @for (f of fields; track f.key) {
            <label class="field"><span>{{ f.label }}</span>
              <input inputmode="decimal" [disabled]="!auth.isAdmin()" [ngModel]="form()[f.key]" (ngModelChange)="set(f.key, $event)" [name]="f.key">
              @if (f.hint) { <span class="hint">{{ f.hint }}</span> }</label>
          }
          <label class="field"><span>Modelo</span>
            <select [disabled]="!auth.isAdmin()" [ngModel]="form()['model']" (ngModelChange)="set('model', $event)" name="model">
              @for (m of st.modelos; track m) { <option [value]="m">{{ m }}</option> }
            </select><span class="hint">mais capaz = mais caro por ciclo</span></label>
          <label class="field"><span>Universo</span>
            <input [disabled]="!auth.isAdmin()" [ngModel]="form()['universe']" (ngModelChange)="set('universe', $event)" name="universe">
            <span class="hint">tudo, todos (20 cripto) ou lista: BTC,NVDA,AAPL</span></label>
          <label class="field"><span>Modo</span>
            <select [disabled]="!auth.isAdmin()" [ngModel]="form()['shadow']" (ngModelChange)="set('shadow', $event)" name="shadow">
              <option [ngValue]="false">envia ordens (demo)</option><option [ngValue]="true">sombra (só registra)</option>
            </select><span class="hint">em sombra a IA decide e anota, sem abrir posição</span></label>
          <label class="field"><span>Direção</span>
            <select [disabled]="!auth.isAdmin()" [ngModel]="form()['long_only']" (ngModelChange)="set('long_only', $event)" name="long_only">
              <option [ngValue]="true">só comprado (long)</option><option [ngValue]="false">comprado e vendido</option>
            </select><span class="hint">vendido só se você liberar</span></label>
        </div>
        <div class="row mt">
          <button class="btn primary" [disabled]="busy() || !auth.isAdmin() || !dirty()" (click)="save()">Salvar limites</button>
          <button class="btn ghost" [disabled]="!dirty()" (click)="reset()">Descartar</button>
          @if (dirty()) { <span class="pill warn">alterações não salvas</span> }
        </div>
        <p class="note mt">Por segurança a IA só opera com Kalshi em modo <b>testnet</b> (demo), respeita o kill-switch, nunca abre sem stop e fecha na hora
          qualquer posição que abra sem stop. Ela não vê notícias nem texto da internet: recebe só números do próprio sistema.</p>
      </section>
    } @else {
      <div class="sk" style="height:120px"></div>
    }`,
})
export class AgentPage {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);
  protected readonly auth = inject(AuthService);
  protected readonly fields = FIELDS;
  protected readonly fmt = fmt;
  protected readonly tone = tone;
  protected readonly s = signal<AgentStatus | null>(null);
  protected readonly form = signal<Record<string, unknown>>({});
  private readonly initial = signal<Record<string, unknown>>({});
  protected readonly busy = signal(false);
  protected readonly cfg = computed<AgentConfig>(() => this.s()?.config ?? NO_CONFIG);
  protected readonly livro = computed(() =>
    Object.entries(this.s()?.livro ?? {}).map(([ativo, b]) => ({ ativo, ...b })).sort((a, b) => b.opened_at - a.opened_at));
  protected readonly dirty = computed(() => JSON.stringify(this.form()) !== JSON.stringify(this.initial()));

  constructor() {
    this.load();
    timer(10_000, 10_000).pipe(takeUntilDestroyed(inject(DestroyRef))).subscribe(() => { if (!document.hidden) this.load(); });
  }

  protected load(): void {
    this.api.agent().subscribe({
      next: r => {
        this.s.set(r);
        if (!this.dirty()) {  // nao pisa em edicao em andamento
          const v = Object.fromEntries(Object.entries(r.config).filter(([k]) => k !== 'enabled'));
          this.form.set(v); this.initial.set({ ...v });
        }
      },
      error: e => this.toast.error(`Não consegui ler a IA: ${errMsg(e)}`),
    });
  }

  protected pill(status: string): string { return status === 'executada' ? 'ok' : status === 'recusada' || status === 'sombra' ? 'warn' : 'bad'; }
  protected set(k: string, v: unknown): void { this.form.update(f => ({ ...f, [k]: ['model', 'universe', 'long_only', 'shadow'].includes(k) ? v : v === '' ? '' : Number(v) })); }
  protected reset(): void { this.form.set({ ...this.initial() }); }

  private go(call: ReturnType<ApiService['agentToggle']>, ok: string): void {
    this.busy.set(true);
    call.subscribe({
      next: () => { this.busy.set(false); this.toast.ok(ok); this.load(); },
      error: e => { this.busy.set(false); this.toast.error(`Falhou: ${errMsg(e)}`); },
    });
  }

  protected async turnOn(): Promise<void> {
    const c = this.cfg();
    if (!(await this.confirmSvc.ask({
      title: 'Ligar a IA para operar?', confirmLabel: 'Ligar',
      body: `Ela vai decidir e operar sozinha na conta DEMO da Kalshi, a cada ${c.interval_min} min, com até ${c.max_usd} USD por entrada, ` +
        `${c.max_positions} posições e perda máxima de ${c.max_daily_loss} USD por dia. Cada ciclo custa uma chamada ao modelo (${c.model}).`,
    }))) return;
    this.go(this.api.agentToggle(true), 'IA ligada');
  }

  protected toggle(on: boolean): void { this.go(this.api.agentToggle(on), on ? 'IA ligada' : 'IA desligada: nenhuma ordem nova; stops e posições continuam na corretora'); }
  protected runNow(): void { this.go(this.api.agentRun(), 'Ciclo disparado: o resultado aparece em ~1 min'); }

  protected save(): void {
    const body = { ...this.form() };
    this.go(this.api.agentConfig(body), 'Limites salvos');
  }
}

export type { AgentDecision };
