import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errMsg } from '../core/api.service';
import { Market, MarketsService } from '../core/markets.service';
import { AuthService } from '../core/auth.service';
import { runAction } from '../core/action';
import { SettingsResponse } from '../core/models';
import { StatusStore } from '../core/status.store';
import { ConfirmService } from '../shared/confirm';
import { Icon } from '../shared/icon';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

export const SETTING_KEYS = ['QUANT_MODE', 'QUANT_VENUE', 'QUANT_TIMEFRAME', 'QUANT_QTY', 'QUANT_MAX_DAILY_LOSS',
                             'QUANT_STOP_ATR', 'QUANT_ASSETS', 'QUANT_NOTIONAL', 'QUANT_MAX_TOTAL_LOSS', 'QUANT_DIRECTION'] as const;
type Key = (typeof SETTING_KEYS)[number];

const LABEL: Record<Key, string> = {
  QUANT_MODE: 'modo', QUANT_VENUE: 'corretora', QUANT_TIMEFRAME: 'timeframe', QUANT_QTY: 'quantidade',
  QUANT_MAX_DAILY_LOSS: 'perda máxima/dia', QUANT_STOP_ATR: 'stop (× ATR)', QUANT_ASSETS: 'ativos', QUANT_DIRECTION: 'direção',
  QUANT_NOTIONAL: 'valor por entrada (USD)', QUANT_MAX_TOTAL_LOSS: 'perda máxima total/dia',
};

@Component({
  selector: 'app-operate',
  imports: [FormsModule, PageHead, Icon],
  styles: `
    .ctl{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
    .venue{display:flex;flex-direction:column;gap:6px}
    .venue.use{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
    .danger-zone{border-color:color-mix(in srgb,var(--bad) 40%,var(--line))}`,
  template: `
    <app-page-head title="Operar" subtitle="Ligue, pare e ajuste o runner. Nada aqui envia ordens por conta própria." />

    <section class="card">
      <div class="ctl">
        <div class="row">
          <span class="pill" [class]="active() ? 'ok' : 'bad'"><span class="dot" [class.pulse]="active()"></span>{{ active() ? 'runner ativo' : 'runner parado' }}</span>
          <span class="sub">serviço <code>quant-live</code></span>
        </div>
        <div class="row">
          <button class="btn primary" [disabled]="!auth.canOperate() || busy() || active()" (click)="act('start', 'Ligar')"><app-icon name="play" [size]="15" /> Ligar</button>
          <button class="btn" [disabled]="!auth.canOperate() || busy()" (click)="act('restart', 'Reiniciar')"><app-icon name="refresh" [size]="15" /> Reiniciar</button>
          <button class="btn" [disabled]="!auth.canOperate() || busy() || !active()" (click)="act('stop', 'Parar')"><app-icon name="stop" [size]="15" /> Parar</button>
        </div>
      </div>
    </section>

    <section class="card mt">
      <div class="card-h">
        <div><h2>Parâmetros</h2><div class="sub">gravados em <code>runtime.env</code>; valem após reiniciar</div></div>
        @if (dirty()) { <span class="pill warn">alterações não salvas</span> }
      </div>
      <div class="grid cols-3">
        <label class="field"><span>Modo</span>
          <select [ngModel]="form()['QUANT_MODE']" (ngModelChange)="set('QUANT_MODE', $event)">
            @for (o of opts('QUANT_MODE'); track o) { <option [value]="o">{{ o }}</option> }
          </select><span class="hint">paper simula; testnet usa a conta de teste da corretora</span></label>
        <label class="field"><span>Corretora</span>
          <select [ngModel]="form()['QUANT_VENUE']" (ngModelChange)="set('QUANT_VENUE', $event)">
            @for (o of opts('QUANT_VENUE'); track o) { <option [value]="o">{{ o }}</option> }
          </select><span class="hint">precisa da chave gravada na VM</span></label>
        <label class="field"><span>Timeframe</span>
          <select [ngModel]="form()['QUANT_TIMEFRAME']" (ngModelChange)="set('QUANT_TIMEFRAME', $event)">
            @for (o of opts('QUANT_TIMEFRAME'); track o) { <option [value]="o">{{ o }}</option> }
          </select><span class="hint">barra usada pela estratégia</span></label>
        <label class="field"><span>Quantidade (ativo)</span>
          <input inputmode="decimal" [ngModel]="form()['QUANT_QTY']" (ngModelChange)="set('QUANT_QTY', $event)">
          <span class="hint">ex.: 0,002 ETH = 2 contratos na Kalshi</span></label>
        <label class="field"><span>Perda máxima por dia</span>
          <input inputmode="decimal" [ngModel]="form()['QUANT_MAX_DAILY_LOSS']" (ngModelChange)="set('QUANT_MAX_DAILY_LOSS', $event)">
          <span class="hint">na moeda da conta; ao passar, o risco trava</span></label>
        <label class="field"><span>Direção</span>
          <select [ngModel]="form()['QUANT_DIRECTION'] || 'both'" (ngModelChange)="set('QUANT_DIRECTION', $event)">
            <option value="both">comprado e vendido (long e short)</option>
            <option value="long">só comprado (long)</option>
          </select><span class="hint">"só comprado" nunca abre short; o sinal de venda só fecha uma compra aberta</span></label>
        <label class="field"><span>Stop (× ATR)</span>
          <input inputmode="decimal" [ngModel]="form()['QUANT_STOP_ATR']" (ngModelChange)="set('QUANT_STOP_ATR', $event)">
          <span class="hint">distância do stop em múltiplos do ATR</span></label>
      </div>
      <div class="row mt">
        <button class="btn primary" [disabled]="!auth.canOperate() || busy() || !dirty()" (click)="save()">Salvar e reiniciar</button>
        <button class="btn ghost" [disabled]="!auth.canOperate() || busy() || !dirty()" (click)="reset()">Descartar</button>
      </div>
      <p class="note mt">Modo <b>live</b> e Polymarket não podem ser ligados por aqui (só por edição na VM).</p>
    </section>

    <section class="card mt">
      <div class="card-h">
        <div><h2>Ativos ({{ picked().size }} de {{ markets.markets().length }})</h2>
          <div class="sub">cada ativo marcado ganha o próprio runner, posição, stop e limite de perda (só Kalshi demo)</div></div>
        <div class="row">
          <button class="btn sm" [disabled]="!auth.canOperate()" (click)="pickCrypto()">Cripto da Binance (20)</button>
          <button class="btn sm" [disabled]="!auth.canOperate()" (click)="pickEverything()">Tudo ({{ markets.markets().length }})</button>
          <button class="btn sm ghost" [disabled]="!auth.canOperate()" (click)="pickNone()">Limpar</button>
        </div>
      </div>
      <input class="mb-3" type="search" placeholder="buscar ativo (ex.: NVDA, ouro, euro)" [ngModel]="query()" (ngModelChange)="query.set($event)" name="q">
      @for (g of visibleGroups(); track g.cls) {
        <div class="mb-3">
          <div class="spread mb-1"><b class="text-[13px] text-mute">{{ g.label }} ({{ g.items.length }})</b>
            <button class="btn ghost sm" [disabled]="!auth.canOperate()" (click)="toggleGroup(g.items)">{{ allPicked(g.items) ? 'desmarcar' : 'marcar' }} todos</button></div>
          <div class="flex flex-wrap gap-1.5">
            @for (m of g.items; track m.id) {
              <button type="button" class="btn sm" [class.primary]="picked().has(m.id)" [disabled]="!auth.canOperate()" [title]="m.title"
                      (click)="toggle(m.id)" [attr.aria-pressed]="picked().has(m.id)">{{ m.id }}</button>
            }
          </div>
        </div>
      } @empty { <p class="note">Nenhum ativo encontrado.</p> }
      <p class="note mt">{{ picked().size ? picked().size + ' ativo(s): a "Quantidade" acima é ignorada e cada entrada vale ~' + (form()['QUANT_NOTIONAL'] || '25') + ' USD.' : 'Nenhum marcado: o runner opera um ativo só (o do modo antigo, com a Quantidade acima).' }}
        Cripto usa preços da Binance; os demais (ações, câmbio, metais…) usam as velas da própria Kalshi. Com muitos ativos, o 1m
        gasta bastante da API: prefira 5m ou 15m.</p>
      <div class="grid cols-3 mt">
        <label class="field"><span>Valor por entrada (USD)</span>
          <input inputmode="decimal" [ngModel]="form()['QUANT_NOTIONAL']" (ngModelChange)="set('QUANT_NOTIONAL', $event)">
          <span class="hint">vira contratos inteiros de cada ativo</span></label>
        <label class="field"><span>Perda máxima total por dia</span>
          <input inputmode="decimal" [ngModel]="form()['QUANT_MAX_TOTAL_LOSS']" (ngModelChange)="set('QUANT_MAX_TOTAL_LOSS', $event)">
          <span class="hint">soma de todos os ativos; ao passar, trava as entradas de todos</span></label>
      </div>
      <p class="note mt">Salve e reinicie em <b>Parâmetros</b> acima para valer.</p>
    </section>

    <h2 class="mt" style="margin-bottom:10px">Corretoras</h2>
    <div class="grid cols-3">
      @for (v of venues(); track v.name) {
        <div class="card venue" [class.use]="v.name === form()['QUANT_VENUE']">
          <div class="spread"><b>{{ v.name }}</b>@if (v.name === form()['QUANT_VENUE']) { <span class="pill accent">em uso</span> }</div>
          <div class="row">@for (m of v.modos; track m) { <span class="pill">{{ m }}</span> } @empty { <span class="pill">só pela VM</span> }</div>
          <span class="sub">{{ v.credencial }}</span>
        </div>
      }
    </div>

    <section class="card mt">
      <div class="spread">
        <div>
          <h2>Destravar a gestão de risco</h2>
          <p class="note">A trava por perda do dia some sozinha na virada do dia (UTC). Aqui você a remove na hora: zera a trava e o PnL
            do dia de todos os ativos e religa o runner. Posições abertas e stops não são tocados.</p>
        </div>
        <button class="btn" [disabled]="!auth.isAdmin() || busy() || killed()" (click)="resetRisk()"><app-icon name="undo" [size]="16" /> Destravar risco</button>
      </div>
    </section>

    <section class="card danger-zone mt">
      <div class="spread">
        <div>
          <h2 class="bad">Kill-switch</h2>
          <p class="note">Fecha a posição, cancela os stops e para o runner de vez. Para retomar é preciso rever a posição e remover o
            arquivo KILL na VM (<code>deploy/README.md</code>).</p>
        </div>
        <button class="btn danger" [disabled]="!auth.canOperate() || killed() || busy()" (click)="kill()"><app-icon name="alert" [size]="16" /> {{ killed() ? 'KILL já acionado' : 'Acionar kill-switch' }}</button>
      </div>
    </section>`,
})
export class OperatePage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly store = inject(StatusStore);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);

  protected readonly settings = signal<SettingsResponse | null>(null);
  protected readonly form = signal<Record<string, string>>({});
  private readonly initial = signal<Record<string, string>>({});
  protected readonly busy = signal(false);
  protected readonly markets = inject(MarketsService);
  protected readonly query = signal('');
  protected readonly picked = computed(() => new Set((this.form()['QUANT_ASSETS'] ?? '').split(',').map(a => a.trim()).filter(Boolean)));
  protected readonly active = computed(() => this.store.data()?.service === 'active');
  protected readonly killed = computed(() => this.store.data()?.kill_file === true);
  protected readonly dirty = computed(() => SETTING_KEYS.some(k => (this.form()[k] ?? '') !== (this.initial()[k] ?? '')));
  protected readonly venues = computed(() =>
    Object.entries(this.store.data()?.venues ?? {}).map(([name, v]) => ({ name, ...v })));

  constructor() { this.load(); this.markets.load(); }

  protected opts(k: Key): string[] {
    const base = this.settings()?.options[k] ?? [];
    const cur = this.form()[k];
    return cur && !base.includes(cur) ? [...base, cur] : base;  // mostra um valor atual fora da lista (ex.: live)
  }

  private load(): void {
    this.api.settings().subscribe({
      next: s => {
        const cur = { ...s.effective, ...s.saved };
        const values: Record<string, string> = {};
        SETTING_KEYS.forEach(k => { if (cur[k] != null) values[k] = cur[k]; });
        this.settings.set(s); this.form.set(values); this.initial.set(values);
      },
      error: e => this.toast.error(`Não consegui ler os parâmetros: ${errMsg(e)}`),
    });
  }

  /** Grupos do catalogo filtrados pela busca (id ou nome). */
  protected readonly visibleGroups = computed(() => {
    const q = this.query().trim().toLowerCase();
    return this.markets.groups()
      .map(g => ({ ...g, items: g.items.filter(m => !q || m.id.toLowerCase().includes(q) || m.title.toLowerCase().includes(q)) }))
      .filter(g => g.items.length);
  });

  private write(ids: Iterable<string>): void {
    const s = new Set(ids);
    this.set('QUANT_ASSETS', this.markets.ids().filter(x => s.has(x)).join(','));  // sempre na ordem do catalogo
  }
  protected toggle(a: string): void {
    const s = new Set(this.picked());
    if (s.has(a)) s.delete(a); else s.add(a);
    this.write(s);
  }
  protected allPicked(items: Market[]): boolean { return items.every(m => this.picked().has(m.id)); }
  protected toggleGroup(items: Market[]): void {
    const s = new Set(this.picked());
    const all = this.allPicked(items);
    items.forEach(m => { if (all) s.delete(m.id); else s.add(m.id); });
    this.write(s);
  }
  protected pickCrypto(): void { this.write(this.markets.binance()); }
  protected pickEverything(): void { this.write(this.markets.ids()); }
  protected pickNone(): void { this.set('QUANT_ASSETS', ''); }

  protected set(k: Key, v: string): void { this.form.update(f => ({ ...f, [k]: v })); }
  protected reset(): void { this.form.set({ ...this.initial() }); }

  protected async act(verb: 'start' | 'stop' | 'restart', label: string): Promise<void> {
    if (verb !== 'start' && !(await this.confirmSvc.ask({ title: `${label} o runner?`, confirmLabel: label,
        body: verb === 'stop' ? 'Parar não fecha a posição aberta nem cancela os stops da corretora.' : 'O estado e a posição são preservados.' }))) return;
    this.busy.set(true);
    runAction(this.toast, this.api.runner(verb), () => `Runner: ${label.toLowerCase()} ok`, () => { this.busy.set(false); this.store.refresh(); });
  }

  protected async save(): Promise<void> {
    const body: Record<string, string> = {};
    const changes: string[] = [];
    SETTING_KEYS.forEach(k => {
      const v = (this.form()[k] ?? '').toString().trim();
      if (v || k === 'QUANT_ASSETS') body[k] = v;  // ativos vazio = voltar ao modo de um ativo só
      if (v !== (this.initial()[k] ?? '')) changes.push(`${LABEL[k]}: ${this.initial()[k] ?? '—'} → ${v || '—'}`);
    });
    if (!(await this.confirmSvc.ask({ title: 'Salvar e reiniciar o runner?', confirmLabel: 'Salvar e reiniciar', body: changes.join('\n') }))) return;
    this.busy.set(true);
    this.api.saveSettings(body).subscribe({
      next: () => runAction(this.toast, this.api.runner('restart'), () => 'Parâmetros salvos e runner reiniciado',
                            () => { this.busy.set(false); this.load(); this.store.refresh(); }),
      error: e => { this.toast.error(`Falhou: ${errMsg(e)}`); this.busy.set(false); },
    });
  }

  protected async resetRisk(): Promise<void> {
    const ok = await this.confirmSvc.ask({
      title: 'Destravar a gestão de risco?', confirmLabel: 'Destravar', danger: true,
      body: 'Para o runner, zera a trava e o PnL do dia de todos os ativos e religa. Os limites de perda voltam a contar do zero agora.',
    });
    if (!ok) return;
    this.busy.set(true);
    runAction(this.toast, this.api.resetRisk(), r => `Risco destravado em ${r.reset ?? 0} ativo(s)${r.religado ? ' e runner religado' : ''}`,
              () => { this.busy.set(false); this.store.refresh(); });
  }

  protected async kill(): Promise<void> {
    const ok = await this.confirmSvc.ask({
      title: 'Acionar o kill-switch?', danger: true, confirmLabel: 'Acionar kill-switch', requireText: 'KILL',
      body: 'Fecha a posição, cancela os stops e para o runner de vez. Isto não liga nada nem envia ordens novas.',
    });
    if (!ok) return;
    this.busy.set(true);
    runAction(this.toast, this.api.kill(), () => 'Kill-switch acionado: o runner vai fechar a posição e parar',
              () => { this.busy.set(false); this.store.refresh(); });
  }
}
