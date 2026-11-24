import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { filter, switchMap, take, timeout, timer } from 'rxjs';
import { ApiService, errMsg } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { fmt, tone } from '../core/format';
import { OrderRequest, OrderResult, Tone } from '../core/models';
import { StatusStore } from '../core/status.store';
import { ConfirmService } from '../shared/confirm';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { PageHead } from '../shared/page-head';
import { ToastService } from '../shared/toast';

const CONTRACT = 0.001;          // 1 contrato do perp ETH da Kalshi = 0,001 ETH
const PRESETS = [0.005, 0.01, 0.02, 0.05];
const MAX_QTY = 0.05;

@Component({
  selector: 'app-ticket',
  imports: [FormsModule, RouterLink, PageHead, Icon, Kpi],
  styles: `
    .buy{background:var(--ok);border-color:var(--ok);color:#04130c}.buy:hover:not(:disabled){filter:brightness(1.08);border-color:var(--ok)}
    .sell{background:var(--bad);border-color:var(--bad);color:#1c0707}.sell:hover:not(:disabled){filter:brightness(1.08);border-color:var(--bad)}
    .big{padding:13px 18px;font-size:15px;flex:1}
    .presets{display:flex;gap:6px;flex-wrap:wrap}
    .presets button.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
    .lock{display:flex;gap:10px;align-items:flex-start}.lock app-icon{color:var(--warn);margin-top:2px}
    .two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:640px){.two{grid-template-columns:1fr}}`,
  template: `
    <app-page-head title="Boleta" subtitle="Compre, venda, proteja e feche a mão. Só na conta demo da Kalshi (dinheiro de teste).">
      <button class="btn" [disabled]="!auth.canOperate() || busy()" (click)="refresh()"><app-icon name="refresh" [size]="16" /> Atualizar posição</button>
    </app-page-head>

    @if (!demoOk()) {
      <section class="card lock">
        <app-icon name="alert" />
        <div><b>Boleta indisponível neste modo.</b>
          <p class="note">Ela só opera com corretora <code>kalshi</code> em modo <code>testnet</code> (demo). Hoje:
            {{ cfg()['QUANT_VENUE'] || '—' }} / {{ cfg()['QUANT_MODE'] || '—' }}. Ajuste em <a routerLink="/operar">Operar</a>.</p></div>
      </section>
    } @else {
      <div class="grid cols-3">
        <app-kpi label="posição" [value]="posLabel()" [tone]="posTone()" [sub]="posSub()" />
        <app-kpi label="resultado em aberto" [value]="upnl()" [tone]="upnlTone()" [sub]="markSub()" />
        <app-kpi label="stop na corretora" [value]="stopLabel()" [tone]="stopTone()" [sub]="pos() ? 'protege a posição se o preço virar' : ''" />
      </div>

      @if (runnerActive()) {
        <section class="card lock mt">
          <app-icon name="alert" />
          <div><b>O runner está ligado.</b>
            <p class="note">Para abrir ou proteger a mão, pare o robô em <a routerLink="/operar">Operar</a>: os dois não podem mandar na mesma
              posição. Fechar e consultar continuam liberados.</p></div>
        </section>
      }

      <section class="card mt">
        <div class="card-h"><div><h2>Nova ordem</h2><div class="sub">a mercado, com limite de 1% de derrapagem</div></div></div>
        <div class="two">
          <label class="field"><span>Quantidade (ETH)</span>
            <input type="number" inputmode="decimal" step="0.001" min="0.001" [max]="max" [ngModel]="qty()" (ngModelChange)="qty.set(+$event)" name="qty">
            <span class="hint">= {{ contracts() }} contrato(s) · máx {{ max }} ETH por ordem</span></label>
          <label class="field"><span>Stop (% do preço de entrada)</span>
            <input type="number" inputmode="decimal" step="0.1" min="0.1" max="20" [ngModel]="stopPct()" (ngModelChange)="stopPct.set(+$event)" name="stop">
            <span class="hint">vazio ou 0 = sem stop (não recomendado)</span></label>
        </div>
        <div class="presets mt">
          @for (p of presets; track p) {
            <button class="btn sm" [class.on]="qty() === p" (click)="qty.set(p)">{{ p }}</button>
          }
        </div>
        <div class="row mt">
          <button class="btn big buy" [disabled]="!canOpen()" (click)="open(1)">Comprar (long)</button>
          <button class="btn big sell" [disabled]="!canOpen()" (click)="open(-1)">Vender (short)</button>
        </div>
        @if (!qtyOk()) { <p class="note mt">Informe uma quantidade entre 0,001 e {{ max }} ETH.</p> }
      </section>

      <section class="card mt">
        <div class="card-h"><h2>Posição aberta</h2></div>
        @if (pos(); as p) {
          <p class="note">{{ p.side > 0 ? 'LONG' : 'SHORT' }} de {{ p.qty }} ETH, entrada em {{ fmt(p.entry) }}.</p>
          <div class="row mt">
            <button class="btn danger" [disabled]="!auth.canOperate() || busy()" (click)="close()">Fechar posição</button>
            <button class="btn" [disabled]="!auth.canOperate() || busy() || runnerActive() || !stopOk()" (click)="applyStop()">Recolocar stop de {{ stopPct() }}%</button>
          </div>
        } @else {
          <div class="empty"><b>Sem posição</b>Abra uma ordem acima. Ela aparece aqui e em Trades quando fechar.</div>
        }
      </section>

      @if (result(); as r) {
        <section class="card mt">
          <div class="row"><span class="pill" [class]="r.ok ? 'ok' : 'bad'">{{ r.ok ? 'ok' : 'recusada' }}</span><span>{{ r.msg }}</span></div>
          @if (r.aviso) { <p class="note mt warn">{{ r.aviso }}</p> }
        </section>
      }
      @if (busy()) { <p class="note mt">Enviando para a corretora…</p> }
    }`,
})
export class TicketPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly store = inject(StatusStore);
  private readonly toast = inject(ToastService);
  private readonly confirmSvc = inject(ConfirmService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly presets = PRESETS;
  protected readonly max = MAX_QTY;
  protected readonly fmt = fmt;
  protected readonly qty = signal(0.01);
  protected readonly stopPct = signal<number | null>(1);
  protected readonly busy = signal(false);
  protected readonly result = signal<OrderResult | null>(null);
  private readonly lastPos = signal<OrderResult['position']>(undefined);

  protected readonly cfg = computed(() => this.store.data()?.config ?? {});
  protected readonly demoOk = computed(() => this.store.data() == null || (this.cfg()['QUANT_MODE'] === 'testnet' && this.cfg()['QUANT_VENUE'] === 'kalshi'));
  protected readonly runnerActive = computed(() => this.store.data()?.service === 'active');
  protected readonly qtyOk = computed(() => this.qty() >= CONTRACT && this.qty() <= MAX_QTY);
  protected readonly stopOk = computed(() => (this.stopPct() ?? 0) >= 0.1 && (this.stopPct() ?? 0) <= 20);
  protected readonly contracts = computed(() => Math.round(this.qty() / CONTRACT));
  protected readonly canOpen = computed(() => this.auth.canOperate() && !this.busy() && !this.runnerActive() && this.qtyOk() && !this.pos());

  protected readonly pos = computed(() => this.lastPos() ?? null);
  protected readonly posLabel = computed(() => { const p = this.pos(); return p ? (p.side > 0 ? 'LONG' : 'SHORT') : 'sem posição'; });
  protected readonly posTone = computed<Tone>(() => { const p = this.pos(); return p ? (p.side > 0 ? 'ok' : 'bad') : ''; });
  protected readonly posSub = computed(() => { const p = this.pos(); return p ? `${p.qty} ETH @ ${fmt(p.entry)}` : 'aguardando sua ordem'; });
  protected readonly upnl = computed(() => { const p = this.pos(); return p?.upnl == null ? '—' : fmt(p.upnl, 4); });
  protected readonly upnlTone = computed<Tone>(() => tone(this.pos()?.upnl ?? null));
  protected readonly markSub = computed(() => { const p = this.pos(); return p?.price == null ? '' : `preço agora ${fmt(p.price)}`; });
  protected readonly stopLabel = computed(() => { const p = this.pos(); return !p ? '—' : p.stop ? 'protegida' : p.stop === false ? 'SEM STOP' : 'desconhecido'; });
  protected readonly stopTone = computed<Tone>(() => { const p = this.pos(); return !p ? '' : p.stop ? 'ok' : 'bad'; });

  constructor() {
    if (this.demoOk() && this.auth.canOperate()) this.refresh(true);
  }

  protected refresh(silent = false): void {
    this.send({ action: 'status' }, silent);
  }

  protected async open(side: 1 | -1): Promise<void> {
    const pct = this.stopOk() ? this.stopPct()! : null;
    const dir = side > 0 ? 'COMPRAR (long)' : 'VENDER (short)';
    const ok = await this.confirmSvc.ask({
      title: `${dir} ${this.qty()} ETH?`, confirmLabel: side > 0 ? 'Comprar' : 'Vender', danger: side < 0,
      body: `Conta demo da Kalshi (dinheiro de teste). ${this.contracts()} contrato(s) a mercado, ` +
        (pct ? `com stop de ${pct}% do preço de entrada.` : 'SEM stop: a perda não tem limite automático.'),
    });
    if (ok) this.send({ action: 'open', side, qty: this.qty(), stop_pct: pct });
  }

  protected async close(): Promise<void> {
    if (await this.confirmSvc.ask({ title: 'Fechar a posição?', confirmLabel: 'Fechar', danger: true,
        body: 'Fecha tudo a mercado e cancela o stop. O resultado entra no histórico de trades.' })) {
      this.send({ action: 'close' });
    }
  }

  protected applyStop(): void { this.send({ action: 'stop', stop_pct: this.stopPct() }); }

  /** Envia o pedido e espera o resultado: a unit oneshot grava `order-result.json` com o mesmo id. */
  private send(req: OrderRequest, silent = false): void {
    this.busy.set(true);
    this.api.order(req).pipe(
      switchMap(r => timer(800, 1000).pipe(switchMap(() => this.api.orderResult()), filter(x => x.id === r.id), take(1))),
      timeout(75_000),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: res => {
        this.busy.set(false);
        this.lastPos.set(res.position ?? null);
        if (!silent || res.ok === false) this.result.set(res);
        if (res.ok === false) this.toast.error(res.msg ?? 'ordem recusada');
        else if (!silent) this.toast.ok(res.msg ?? 'ok');
        if (req.action !== 'status') this.store.refresh();
      },
      error: e => {
        this.busy.set(false);
        const msg = e?.name === 'TimeoutError' ? 'a corretora não respondeu a tempo; confira a posição e tente de novo' : errMsg(e);
        this.toast.error(`Falhou: ${msg}`);
      },
    });
  }
}
