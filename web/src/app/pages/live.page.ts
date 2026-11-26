import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Subject, catchError, filter, forkJoin, merge, of, switchMap, timer } from 'rxjs';
import { ApiService, errMsg } from '../core/api.service';
import { dur, fmt, hhmm, tone } from '../core/format';
import { FlowSeries, Live, LiveCandidate, RadarRow } from '../core/models';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { LineChart } from '../shared/line-chart';
import { PageHead } from '../shared/page-head';

export const LIVE_POLL_MS = 10000;

const RESULTADO: Record<string, string> = {
  ok: 'sem sinal', entrada: 'entrou', stop: 'saiu no stop', saida_sinal: 'saiu por sinal', sem_fluxo: 'sinal sem apoio do fluxo',
  bloqueada: 'bloqueada pelo risco', sem_margem: 'sem margem', sem_protecao: 'sem stop protetor', lacuna: 'lacuna de dados',
};

/** Cor de fundo de uma celula: verde para positivo, vermelho para negativo, mais forte quanto maior o modulo. */
export function heat(v: number | null | undefined, full: number): string {
  if (v == null || !Number.isFinite(v) || v === 0) return 'transparent';
  const a = Math.round(Math.min(Math.abs(v) / full, 1) * 32);
  return `color-mix(in srgb, var(${v > 0 ? '--ok' : '--bad'}) ${a}%, transparent)`;
}

@Component({
  selector: 'app-live',
  imports: [Kpi, PageHead, Icon, LineChart],
  styles: `
    .funil{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
    .funil div{background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
    .funil b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
    .funil span{font-size:12px;color:var(--mute)}
    td.h{text-align:right;border-radius:4px}
    tr.pick{cursor:pointer}
    tr.sel{background:var(--accent-soft)}
    .seg{display:inline-flex;border:1px solid var(--line-strong);border-radius:10px;overflow:hidden}
    .seg button{font:inherit;font-size:13px;font-weight:600;padding:6px 13px;border:none;background:transparent;color:var(--mute);cursor:pointer}
    .seg button.on{background:var(--accent-soft);color:var(--accent)}
    .hist{display:flex;align-items:flex-end;gap:2px;height:44px}
    .hist i{flex:1;background:var(--line-strong);border-radius:2px;min-height:3px}
    .hist i.on{background:var(--accent)}
    @media(max-width:640px){.funil{grid-template-columns:repeat(3,minmax(0,1fr))}}`,
  template: `
    <app-page-head title="Ao vivo" subtitle="O que a IA e o robô estão lendo agora, e por que agem ou ficam parados">
      <button class="btn" (click)="paused.set(!paused())"><app-icon [name]="paused() ? 'refresh' : 'pulse'" [size]="16" /> {{ paused() ? 'Retomar' : 'Pausar' }}</button>
    </app-page-head>

    @if (error()) { <div class="alert bad" role="alert"><app-icon name="alert" [size]="18" /> <span>Não consegui ler: {{ error() }}</span></div> }

    @if (d(); as d) {
      <div class="row">
        @for (f of d.fontes; track f.nome) {
          <span class="pill" [class]="fresh(f.idade_s, f.limite_s)" [title]="f.detalhe"><span class="dot"></span>{{ f.nome }}: {{ f.idade_s == null ? 'sem dado' : 'há ' + dur(f.idade_s) }}</span>
        }
      </div>

      <section class="card mt">
        <div class="card-h"><h2>Raciocínio da IA</h2>
          @if (d.ia; as ia) { <span class="sub">{{ ia.modelo }} · há {{ dur(ia.ha_s) }} · {{ ia.sombra ? 'em sombra' : 'enviando ordens' }}</span> }
        </div>
        @if (d.ia; as ia) {
          <div class="funil">
            <div><b>{{ ia.funil.universo }}</b><span>ativos no universo</span></div>
            <div><b>{{ ia.funil.fotos }}</b><span>com livro utilizável</span></div>
            <div><b>{{ ia.funil.candidatos }}</b><span>analisados</span></div>
            <div><b>{{ ia.funil.pedidos }}</b><span>ações pedidas</span></div>
            <div><b>{{ ia.funil.aceitos }}</b><span>aceitas pelo código</span></div>
          </div>
          @if (ia.erro) { <div class="alert bad mt" role="alert"><span>{{ ia.erro }}</span></div> }
          <p class="note mt">{{ ia.analise || 'sem análise neste ciclo' }}</p>
          <div class="hist mt" role="img" aria-label="ações aceitas nos últimos ciclos">
            @for (h of ia.historico; track h.t) { <i [class.on]="h.aceitos > 0" [style.height.%]="20 + 25 * h.pedidos" [title]="when(h.t) + ': ' + h.aceitos + ' de ' + h.pedidos + ' aceitas'"></i> }
          </div>
          <p class="sub">Últimos {{ ia.historico.length }} ciclos: a altura é o número de pedidos; em destaque, os que tiveram ação aceita.</p>

          <div class="scroll-x mt"><table>
            <thead><tr><th>ativo</th><th class="r">5 min</th><th class="r">15 min</th><th class="r">60 min</th><th class="r">livro 1%</th><th class="r">spread</th><th class="r">custo</th><th>decisão</th></tr></thead>
            <tbody>
              @for (c of candidates(); track c.ativo) {
                <tr class="pick" [class.sel]="asset() === c.ativo" (click)="pick(c.ativo)">
                  <td><b>{{ c.ativo }}</b></td>
                  <td class="h" [style.background]="heat(c.ret_5m_bps, 40)">{{ ret(c.ret_5m_bps) }}</td>
                  <td class="h" [style.background]="heat(c.ret_15m_bps, 80)">{{ ret(c.ret_15m_bps) }}</td>
                  <td class="h" [style.background]="heat(c.ret_60m_bps, 150)">{{ ret(c.ret_60m_bps) }}</td>
                  <td class="h" [style.background]="heat(c.imb_100, 1)">{{ fmt(c.imb_100) }}</td>
                  <td class="r">{{ ret(c.spread_bps) }}</td>
                  <td class="r">{{ ret(c.custo_ida_volta_bps) }}</td>
                  <td>@if (c.status) { <span class="pill" [class]="statusTone(c.status)">{{ c.decisao }} · {{ c.status }}</span> <span class="sub">{{ c.porque }}</span> } @else { <span class="faint">ignorado</span> }</td>
                </tr>
              } @empty { <tr><td colspan="8" class="sub">este ciclo não gravou candidatos</td></tr> }
            </tbody>
          </table></div>
          <p class="sub mt">Retornos, spread e custo em %. "Livro 1%" vai de −1 (só venda) a +1 (só compra). Clique num ativo para ver a leitura dele.</p>
        } @else { <div class="empty">a IA ainda não registrou nenhum ciclo</div> }
      </section>

      <section class="card mt">
        <div class="card-h"><h2>Leitura do ativo</h2>
          <div class="row">
            <select [value]="asset()" (change)="pick($any($event.target).value)" aria-label="ativo" style="width:auto">
              <option value="">escolha…</option>
              @for (a of d.ativos; track a) { <option [value]="a" [selected]="a === asset()">{{ a }}</option> }
            </select>
            <div class="seg" role="group" aria-label="janela">
              @for (h of windows; track h) { <button [class.on]="hours() === h" (click)="setHours(h)">{{ h }} h</button> }
            </div>
          </div>
        </div>
        @if (series(); as s) {
          <h2>Preço (meio do livro)</h2>
          <app-line-chart [values]="prices()" [labels]="times()" [height]="200" [format]="price" label="preço" empty="sem fotos deste ativo na janela" />
          <h2 class="mt">Desequilíbrio do livro (1%)</h2>
          <app-line-chart [values]="imbalance()" [labels]="times()" [height]="140" [baseline]="0" label="desequilíbrio do livro" empty="sem fotos deste ativo na janela" />
          @if (s.decisoes.length) {
            <h2 class="mt">O que a IA pediu para {{ s.ativo }}</h2>
            <div class="list mt">
              @for (x of s.decisoes; track x.t + (x.acao ?? '')) {
                <div><span class="sub">{{ when(x.t) }}</span> <span class="pill" [class]="statusTone(x.status)">{{ x.acao }} · {{ x.status }}</span> <span>{{ x.porque }}</span></div>
              }
            </div>
          }
        } @else { <div class="empty">escolha um ativo para ver preço, fluxo e decisões</div> }
      </section>

      <section class="card mt">
        <div class="card-h"><h2>Radar do robô</h2><span class="sub">entra quando rompe o canal, na direção da tendência, com ER ≥ {{ fmt(d.er_min) }}</span></div>
        <div class="grid cols-3">
          <app-kpi label="ativos vigiados" [value]="'' + d.robo.length" [sub]="open() + ' com posição'" />
          <app-kpi label="em regime de tendência" [value]="'' + trending()" sub="ER acima do mínimo" />
          <app-kpi label="travados" [value]="'' + halted()" [tone]="halted() ? 'warn' : 'ok'" sub="trava de risco ligada" />
        </div>
        <div class="scroll-x mt"><table>
          <thead><tr><th>ativo</th><th>situação</th><th>tendência</th><th class="r">falta subir</th><th class="r">falta cair</th><th class="r">ER</th><th class="r">livro 1%</th></tr></thead>
          <tbody>
            @for (r of d.robo; track r.ativo) {
              <tr class="pick" [class.sel]="asset() === r.ativo" (click)="pick(r.ativo)">
                <td><b>{{ r.ativo }}</b></td><td>{{ state(r) }}</td>
                <td>{{ r.tendencia === 1 ? 'alta' : r.tendencia === -1 ? 'baixa' : '—' }}</td>
                <td class="r">{{ gap(r.falta_alta_pct) }}</td><td class="r">{{ gap(r.falta_baixa_pct) }}</td>
                <td class="r" [class.ok]="r.er_ok">{{ fmt(r.er) }}</td>
                <td class="h" [style.background]="heat(r.fluxo, 1)">{{ fmt(r.fluxo) }}</td>
              </tr>
            } @empty { <tr><td colspan="7" class="sub">o robô não tem ativos configurados</td></tr> }
          </tbody>
        </table></div>
      </section>
    } @else if (!error()) { <div class="card"><div class="empty">carregando…</div></div> }`,
})
export class LivePage {
  private readonly api = inject(ApiService);
  private readonly manual = new Subject<void>();
  protected readonly windows = [1, 6, 24];

  protected readonly d = signal<Live | null>(null);
  protected readonly series = signal<FlowSeries | null>(null);
  protected readonly asset = signal('');
  protected readonly hours = signal(6);
  protected readonly paused = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly candidates = computed<LiveCandidate[]>(() => {
    const list = this.d()?.ia?.candidatos ?? [];
    return [...list].sort((a, b) => Number(!!b.status) - Number(!!a.status));
  });
  protected readonly prices = computed(() => (this.series()?.serie ?? []).map(p => p[1]));
  protected readonly imbalance = computed(() => (this.series()?.serie ?? []).map(p => p[2]));
  protected readonly times = computed(() => (this.series()?.serie ?? []).map(p => hhmm(p[0] * 1000)));
  protected readonly open = computed(() => (this.d()?.robo ?? []).filter(r => r.posicao != null).length);
  protected readonly trending = computed(() => (this.d()?.robo ?? []).filter(r => r.er_ok).length);
  protected readonly halted = computed(() => (this.d()?.robo ?? []).filter(r => r.travado).length);

  protected readonly fmt = fmt;
  protected readonly dur = dur;
  protected readonly tone = tone;
  protected readonly heat = heat;
  protected price = (v: number) => fmt(v, v >= 100 ? 2 : v >= 1 ? 4 : 6);
  protected ret = (bps: number | null | undefined) => (bps == null ? '—' : fmt(bps / 100, 2));
  protected gap = (p: number | null) => (p == null ? '—' : p <= 0 ? 'rompeu' : fmt(p, 2) + '%');
  protected when = (s: number) => new Date(s * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  protected fresh = (age: number | null, limit: number) => (age == null ? 'bad' : age > limit ? 'warn' : 'ok');
  protected statusTone = (s: string | null | undefined) => (s === 'executada' ? 'ok' : s === 'falhou' ? 'bad' : 'warn');
  protected state(r: RadarRow): string {
    if (r.travado) return 'travado: ' + r.motivo;
    if (r.posicao != null) return r.posicao > 0 ? 'comprado' : 'vendido';
    if (!r.barra) return 'sem barra ainda';
    return r.resultado ? (RESULTADO[r.resultado] ?? r.resultado) : 'aguardando a próxima barra';
  }

  constructor() {
    merge(timer(0, LIVE_POLL_MS).pipe(filter(() => !this.paused())), this.manual).pipe(
      filter(() => typeof document === 'undefined' || !document.hidden),
      switchMap(() => forkJoin({
        live: this.api.live(),
        flow: this.asset() ? this.api.flow(this.asset(), this.hours()) : of(null),
      }).pipe(catchError(e => { this.error.set(errMsg(e)); return EMPTY; }))),
      takeUntilDestroyed(inject(DestroyRef)),
    ).subscribe(({ live, flow }) => { this.d.set(live); this.series.set(flow); this.error.set(null); });
  }

  protected pick(a: string): void {
    if (a === this.asset()) return;
    this.asset.set(a);
    this.series.set(null);
    this.manual.next();
  }

  protected setHours(h: number): void { this.hours.set(h); this.manual.next(); }
}
