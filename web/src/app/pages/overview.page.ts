import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ChartLine } from '../core/chart';
import { dur, filterLog, fmt, hhmm, logTone, pct, TIMEFRAME_S, tone } from '../core/format';
import { Tone } from '../core/models';
import { StatusStore } from '../core/status.store';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { LineChart } from '../shared/line-chart';
import { PageHead } from '../shared/page-head';

const MODE_NOTE: Record<string, string> = {
  paper: 'simulado, sem ordens reais', testnet: 'ambiente de teste da corretora', live: 'ATENÇÃO: conta real',
};

interface PositionView { side: number; qty: number; entry: number }

@Component({
  selector: 'app-overview',
  imports: [Kpi, LineChart, PageHead, Icon, RouterLink, FormsModule],
  styles: `
    .hero{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;align-items:center}
    .hero h2{font-size:22px;margin:10px 0 8px}
    .chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    .price{text-align:right}
    .price .p{font-size:34px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
    @media(max-width:640px){.price{text-align:left}}
    .tr{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center}
    .tr .d{font-size:13.5px}
    .chk{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit}
    .chk:hover .t{color:var(--accent)}
    .chk .ico{display:grid;place-items:center;width:36px;height:36px;border-radius:10px;background:var(--surface-2);flex:none}
    .chk .ico.ok{background:var(--ok-soft);color:var(--ok)}.chk .ico.bad{background:var(--bad-soft);color:var(--bad)}.chk .ico.warn{background:var(--warn-soft);color:var(--warn)}
    .chk .t{font-weight:600;font-size:14px}`,
  template: `
    <app-page-head title="Visão geral" subtitle="Estado do runner, posição e atividade recente" />
    @if (d(); as d) {
      <section class="card hero">
        <div>
          <span class="pill" [class]="active() ? store.banner().tone || 'ok' : 'bad'"><span class="dot" [class.pulse]="store.banner().tone === 'ok'"></span>{{ heroPill() }}</span>
          <h2>{{ d.asset || cfg()['QUANT_SYMBOL'] || '—' }} · {{ cfg()['QUANT_TIMEFRAME'] || '—' }}</h2>
          <div class="chips">
            <span class="pill" [class]="cfg()['QUANT_MODE'] === 'paper' ? '' : 'warn'">{{ cfg()['QUANT_MODE'] || '—' }}</span>
            <span class="pill accent">{{ cfg()['QUANT_VENUE'] || 'binance' }}</span>
            <span class="sub">{{ modeNote() }} · ativo há {{ dur(d.health.uptime_s) }} · {{ d.health.memory_mb ?? '—' }} MB</span>
          </div>
        </div>
        <div class="price">
          <div class="sub">último preço (feed público)</div>
          <div class="p num">{{ lastPrice() }}</div>
          <div class="num" [class]="windowTone()">{{ windowChange() }}</div>
        </div>
      </section>

      @if (d.assets?.length) {
        <section class="card mt">
          <div class="card-h">
            <div><h2>Ativos em operação ({{ d.assets!.length }})</h2>
              <div class="sub">{{ openCount() }} posição(ões) aberta(s) · PnL do dia somado
                <b class="num" [class]="tone(totalPnl())">{{ fmt(totalPnl(), 4) }}</b> · clique num ativo para ver o gráfico dele</div></div>
          </div>
          @if (d.assets!.length > 8) {
            <div class="row mb-3">
              <input class="!w-64" type="search" placeholder="filtrar (ex.: NVDA)" [ngModel]="filter()" (ngModelChange)="filter.set($event)" name="f">
              <label class="flex cursor-pointer items-center gap-2 text-[13.5px] text-mute"><input class="w-auto" type="checkbox"
                [ngModel]="onlyOpen()" (ngModelChange)="onlyOpen.set($event)" name="o"> só com posição ou travados</label>
              <span class="sub">{{ rows().length }} de {{ d.assets!.length }}</span>
            </div>
          }
          <div class="scroll-x max-h-[420px] overflow-y-auto"><table>
            <thead><tr><th>Ativo</th><th>Posição</th><th class="r">PnL do dia</th><th class="r">Trades</th><th>Última barra</th><th>Estado</th></tr></thead>
            <tbody>
              @for (a of rows(); track a.asset) {
                <tr class="cursor-pointer" [class.bg-accent-soft]="a.asset === d.asset" (click)="store.select(a.asset)" tabindex="0" (keydown.enter)="store.select(a.asset)">
                  <td><b>{{ a.asset }}</b></td>
                  <td>@if (a.position) { <span class="pill" [class]="a.position.side > 0 ? 'ok' : 'bad'">{{ a.position.side > 0 ? 'LONG' : 'SHORT' }}</span> <span class="sub num">@ {{ fmt(a.position.price) }}</span> } @else { <span class="sub">—</span> }</td>
                  <td class="r num" [class]="tone(a.pnl)">{{ fmt(a.pnl, 4) }}</td>
                  <td class="r num">{{ a.trades }}</td>
                  <td class="sub">{{ a.last_bar_age_s == null ? '—' : 'há ' + dur(a.last_bar_age_s) }}</td>
                  <td>@if (!a.started) { <span class="pill">aguardando</span> } @else if (a.halted) { <span class="pill bad" [title]="a.reason">travado</span> } @else { <span class="pill ok">ok</span> }</td>
                </tr>
              }
            </tbody>
          </table></div>
        </section>
      }

      <div class="grid cols-4 mt">
        <app-kpi label="posição" [value]="positionLabel()" [sub]="positionSub()" [tone]="position() ? (position()!.side > 0 ? 'ok' : 'bad') : ''" />
        <app-kpi label="PnL do dia" [value]="fmt(pnlDay(), 4)" [tone]="pnlTone()" [sub]="(risk().trades ?? 0) + ' trade(s) hoje · perda máx ' + (cfg()['QUANT_MAX_DAILY_LOSS'] || '—')" />
        <app-kpi label="trava de risco" [value]="risk().halted ? 'TRAVADO' : 'livre'" [tone]="risk().halted ? 'bad' : 'ok'" [sub]="risk().halted ? (risk().reason || '') : 'entradas liberadas'" />
        <app-kpi label="última barra" [value]="d.last_bar_age_s == null ? '—' : 'há ' + dur(d.last_bar_age_s)" [tone]="stale() && active() ? 'warn' : ''" [sub]="d.state?.last_bar || 'sem barra processada'" />
      </div>

      <section class="card mt">
        <div class="card-h">
          <div><h2>Preço recente</h2><div class="sub">{{ chartNote() }}</div></div>
        </div>
        <app-line-chart [values]="prices()" [labels]="times()" [lines]="refLines()" [height]="260"
                        label="preço recente" empty="sem barras: o feed público está indisponível" />
      </section>

      <div class="grid cols-2 mt">
        <section class="card">
          <div class="card-h"><h2>Últimos trades</h2><a class="btn ghost sm" routerLink="/trades">ver todos</a></div>
          @if (d.trades.trades.length) {
            <div class="list">
              @for (t of d.trades.trades.slice(0, 5); track t.ts + t.entrada) {
                <div class="tr">
                  <span class="pill" [class]="t.side > 0 ? 'ok' : 'bad'">{{ t.side > 0 ? 'LONG' : 'SHORT' }}</span>
                  <div class="d num"><span>{{ fmt(t.entrada) }} → {{ fmt(t.saida) }}</span><div class="sub">{{ t.ts.slice(5, 16) }} · {{ t.motivo }}</div></div>
                  <b class="num" [class]="tone(t.pnl)">{{ fmt(t.pnl, 4) }}</b>
                </div>
              }
            </div>
          } @else {
            <div class="empty"><b>Nenhum trade fechado ainda</b>Quando o runner abrir e fechar uma posição, ela aparece aqui.</div>
          }
        </section>

        <section class="card">
          <div class="card-h"><h2>Atividade do runner</h2><a class="btn ghost sm" routerLink="/saude">log completo</a></div>
          @if (activity().length) {
            <pre class="log">@for (l of activity(); track $index) {<span class="l" [class]="logTone(l)">{{ l }}</span>}</pre>
          } @else {
            <div class="empty"><b>Sem eventos importantes</b>Entradas, saídas, avisos e erros aparecem aqui.</div>
          }
        </section>
      </div>

      <div class="grid cols-3 mt">
        <a class="card chk" routerLink="/saude">
          <span class="ico" [class]="d.selfcheck ? (d.selfcheck.ok ? 'ok' : 'bad') : ''"><app-icon [name]="d.selfcheck && !d.selfcheck.ok ? 'alert' : 'check'" /></span>
          <div><div class="t">Autoverificação</div><div class="sub">{{ d.selfcheck ? (d.selfcheck.ok ? 'tudo certo' : 'FALHOU') + (d.selfcheck.tests ? ' · ' + d.selfcheck.tests.passed + ' testes' : '') : 'aguardando 1ª execução' }}</div></div>
        </a>
        <a class="card chk" routerLink="/gestao">
          <span class="ico" [class]="d.alerts.canais.length ? 'ok' : 'warn'"><app-icon name="bell" /></span>
          <div><div class="t">Alertas</div><div class="sub">{{ d.alerts.canais.length ? d.alerts.canais.join(' + ') : 'sem canal configurado' }}</div></div>
        </a>
        <a class="card chk" routerLink="/gestao">
          <span class="ico" [class]="d.deploy.last?.state === 'erro' ? 'bad' : d.deploy.last ? 'ok' : ''"><app-icon name="package" /></span>
          <div><div class="t">Atualização</div><div class="sub">{{ d.deploy.last ? (d.deploy.last.state === 'ok' ? 'aplicada' : d.deploy.last.state) : 'nenhuma ainda' }}{{ d.deploy.pacote ? ' · pacote esperando' : '' }}</div></div>
        </a>
      </div>
    } @else {
      <div class="grid cols-4"><div class="sk" style="height:96px"></div><div class="sk" style="height:96px"></div><div class="sk" style="height:96px"></div><div class="sk" style="height:96px"></div></div>
      <div class="sk mt" style="height:280px"></div>
    }`,
})
export class OverviewPage {
  protected readonly store = inject(StatusStore);
  protected readonly d = this.store.data;
  protected readonly dur = dur;
  protected readonly fmt = fmt;
  protected readonly tone = tone;
  protected readonly logTone = logTone;

  protected readonly filter = signal('');
  protected readonly onlyOpen = signal(false);
  protected readonly rows = computed(() => {
    const q = this.filter().trim().toLowerCase();
    return (this.d()?.assets ?? []).filter(a => (!q || a.asset.toLowerCase().includes(q)) && (!this.onlyOpen() || a.position || a.halted));
  });
  protected readonly openCount = computed(() => (this.d()?.assets ?? []).filter(a => a.position).length);
  protected readonly totalPnl = computed(() => (this.d()?.assets ?? []).reduce((s, a) => s + a.pnl, 0));
  protected readonly cfg = computed(() => this.d()?.config ?? {});
  protected readonly risk = computed(() => this.d()?.state?.risk ?? {});
  protected readonly active = computed(() => this.d()?.service === 'active');
  protected readonly heroPill = computed(() =>
    !this.active() ? 'runner parado' : this.store.banner().tone === 'ok' ? this.store.banner().text : 'runner ativo');
  protected readonly modeNote = computed(() => MODE_NOTE[this.cfg()['QUANT_MODE']] ?? '');
  protected readonly stale = computed(() => {
    const age = this.d()?.last_bar_age_s;
    return age != null && age > (TIMEFRAME_S[this.cfg()['QUANT_TIMEFRAME']] ?? 60) * 3;
  });

  protected readonly position = computed<PositionView | null>(() => {
    const p = this.d()?.state?.executor?.pos as Partial<PositionView> | null | undefined;
    return p && p.side != null ? { side: p.side, qty: p.qty ?? 0, entry: p.entry ?? 0 } : null;
  });
  protected readonly positionLabel = computed(() => {
    const p = this.position();
    return p ? (p.side > 0 ? 'LONG' : 'SHORT') : 'sem posição';
  });
  protected readonly positionSub = computed(() => {
    const p = this.position(), stop = this.d()?.state?.stop;
    return p ? `${p.qty} @ ${fmt(p.entry)} · stop ${stop != null ? fmt(stop) : '—'}` : 'aguardando sinal da estratégia';
  });
  protected readonly entry = computed(() => this.d()?.state?.entry?.price ?? null);
  protected readonly stop = computed(() => this.d()?.state?.stop ?? null);
  protected readonly pnlDay = computed(() => Number(this.risk().pnl ?? 0));
  protected readonly pnlTone = computed<Tone>(() => tone(this.pnlDay()));

  protected readonly prices = computed(() => (this.d()?.bars ?? []).map(b => b[1]));
  protected readonly times = computed(() => (this.d()?.bars ?? []).map(b => hhmm(b[0])));
  protected readonly lastPrice = computed(() => {
    const p = this.prices();
    return p.length ? fmt(p[p.length - 1]) : '—';
  });
  private readonly change = computed(() => {
    const p = this.prices();
    return p.length > 1 ? p[p.length - 1] / p[0] - 1 : null;
  });
  protected readonly windowChange = computed(() => (this.change() == null ? '' : `${pct(this.change())} na janela`));
  protected readonly windowTone = computed<Tone>(() => tone(this.change()));

  protected readonly refLines = computed<ChartLine[]>(() => {
    const out: ChartLine[] = [];
    if (this.entry() != null) out.push({ value: this.entry()!, color: 'var(--ok)', label: `entrada ${fmt(this.entry())}` });
    if (this.stop() != null) out.push({ value: this.stop()!, color: 'var(--bad)', label: `stop ${fmt(this.stop())}` });
    return out;
  });
  protected readonly chartNote = computed(() => {
    const bars = this.d()?.bars ?? [];
    return bars.length < 2 ? '' : `${hhmm(bars[0][0])} → ${hhmm(bars[bars.length - 1][0])} · passe o mouse para ver cada barra`;
  });
  protected readonly activity = computed(() => filterLog(this.d()?.log ?? [], 'key').slice(-7));
}
