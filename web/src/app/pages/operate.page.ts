import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { Msg, NO_MSG, runAction } from '../core/action';
import { SettingsResponse } from '../core/models';
import { StatusStore } from '../core/status.store';

export const SETTING_KEYS = ['QUANT_MODE', 'QUANT_VENUE', 'QUANT_TIMEFRAME', 'QUANT_QTY', 'QUANT_MAX_DAILY_LOSS',
                             'QUANT_STOP_ATR'] as const;
type Key = (typeof SETTING_KEYS)[number];

@Component({
  selector: 'app-operate',
  imports: [FormsModule],
  template: `
    <h2>Operação do runner</h2>
    <div class="row">
      <button class="act" [disabled]="busy()" (click)="act('start', 'Ligar')">Ligar</button>
      <button class="act" [disabled]="busy()" (click)="act('restart', 'Reiniciar')">Reiniciar</button>
      <button class="act" [disabled]="busy()" (click)="act('stop', 'Parar')">Parar</button>
    </div>
    <div class="grid mt">
      <label class="f">modo
        <select [ngModel]="form()['QUANT_MODE']" (ngModelChange)="set('QUANT_MODE', $event)">
          @for (o of opts('QUANT_MODE'); track o) { <option [value]="o">{{ o }}</option> }
        </select></label>
      <label class="f">corretora
        <select [ngModel]="form()['QUANT_VENUE']" (ngModelChange)="set('QUANT_VENUE', $event)">
          @for (o of opts('QUANT_VENUE'); track o) { <option [value]="o">{{ o }}</option> }
        </select></label>
      <label class="f">timeframe
        <select [ngModel]="form()['QUANT_TIMEFRAME']" (ngModelChange)="set('QUANT_TIMEFRAME', $event)">
          @for (o of opts('QUANT_TIMEFRAME'); track o) { <option [value]="o">{{ o }}</option> }
        </select></label>
      <label class="f">quantidade (ativo)
        <input inputmode="decimal" [ngModel]="form()['QUANT_QTY']" (ngModelChange)="set('QUANT_QTY', $event)"></label>
      <label class="f">perda máxima/dia
        <input inputmode="decimal" [ngModel]="form()['QUANT_MAX_DAILY_LOSS']" (ngModelChange)="set('QUANT_MAX_DAILY_LOSS', $event)"></label>
      <label class="f">stop (× ATR)
        <input inputmode="decimal" [ngModel]="form()['QUANT_STOP_ATR']" (ngModelChange)="set('QUANT_STOP_ATR', $event)"></label>
    </div>

    <div class="card mt">
      @for (v of venues(); track v.name) {
        <div class="s"><b>{{ v.name }}</b>: {{ v.modos.length ? 'modos ' + v.modos.join('/') : 'fora do painel' }} · {{ v.credencial }}</div>
      }
    </div>
    <div class="row mt">
      <button class="act" [disabled]="busy() || !dirty()" (click)="save()">Salvar e reiniciar</button>
      <span class="sub">{{ dirty() ? 'há alterações não salvas' : '' }}</span>
    </div>
    <div class="msg" [class]="msg().tone">{{ msg().text }}</div>
    <p class="note">Modo <b>live</b> e Polymarket não podem ser ligados por aqui (só por edição na VM). <b>testnet</b> e Kalshi exigem
      chaves já gravadas na VM. Salvar grava os parâmetros e reinicia o runner; não envia ordens por conta própria.</p>

    <h2>Kill-switch</h2>
    <div class="row">
      <input style="max-width:200px" placeholder="digite KILL" [ngModel]="confirm()" (ngModelChange)="confirm.set($event)"
             [disabled]="killed()" aria-label="confirmação do kill-switch">
      <button class="kill" [disabled]="killed() || confirm() !== 'KILL' || busy()" (click)="kill()">Acionar kill-switch</button>
      <span class="sub bad">{{ killed() ? 'KILL já acionado' : '' }}</span>
    </div>
    <div class="msg" [class]="killMsg().tone">{{ killMsg().text }}</div>
    <p class="note">Fecha a posição, cancela os stops e para o runner de vez. Não liga nada nem envia ordens: para retomar é preciso
      rever a posição e remover o arquivo KILL na VM (<code>deploy/README.md</code>).</p>`,
})
export class OperatePage {
  private readonly api = inject(ApiService);
  private readonly store = inject(StatusStore);

  protected readonly settings = signal<SettingsResponse | null>(null);
  protected readonly form = signal<Record<string, string>>({});
  private readonly initial = signal<Record<string, string>>({});
  protected readonly busy = signal(false);
  protected readonly msg = signal<Msg>(NO_MSG);
  protected readonly killMsg = signal<Msg>(NO_MSG);
  protected readonly confirm = signal('');
  protected readonly killed = computed(() => this.store.data()?.kill_file === true);
  protected readonly dirty = computed(() => SETTING_KEYS.some(k => (this.form()[k] ?? '') !== (this.initial()[k] ?? '')));
  protected readonly venues = computed(() =>
    Object.entries(this.store.data()?.venues ?? {}).map(([name, v]) => ({ name, ...v })));

  constructor() { this.load(); }

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
      error: () => this.msg.set({ text: 'não consegui ler os parâmetros', tone: 'bad' }),
    });
  }

  protected set(k: Key, v: string): void { this.form.update(f => ({ ...f, [k]: v })); }

  protected act(verb: 'start' | 'stop' | 'restart', label: string): void {
    if (verb !== 'start' && !window.confirm(`${label} o runner?`)) return;
    this.busy.set(true);
    runAction(this.msg, this.api.runner(verb), () => `ok: ${label.toLowerCase()}`, () => { this.busy.set(false); this.store.refresh(); });
  }

  protected save(): void {
    const body: Record<string, string> = {};
    SETTING_KEYS.forEach(k => { const v = (this.form()[k] ?? '').toString().trim(); if (v) body[k] = v; });
    if (!window.confirm(`Salvar estes parâmetros e reiniciar o runner?\n${JSON.stringify(body, null, 1)}`)) return;
    this.busy.set(true);
    this.msg.set({ text: 'salvando…', tone: '' });
    this.api.saveSettings(body).subscribe({
      next: () => runAction(this.msg, this.api.runner('restart'), () => 'salvo e reiniciado',
                            () => { this.busy.set(false); this.load(); this.store.refresh(); }),
      error: e => { this.msg.set({ text: `falhou: ${e?.error?.erro ?? e?.status ?? 'erro'}`, tone: 'bad' }); this.busy.set(false); },
    });
  }

  protected kill(): void {
    this.busy.set(true);
    runAction(this.killMsg, this.api.kill(), () => 'kill-switch acionado: o runner vai fechar a posição e parar',
              () => { this.busy.set(false); this.confirm.set(''); this.store.refresh(); });
  }
}
