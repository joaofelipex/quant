import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Subject, catchError, exhaustMap, filter, merge, timer } from 'rxjs';
import { ApiService, errMsg } from '../core/api.service';
import { dur, fmt, tone } from '../core/format';
import { MetricGroup, Metrics } from '../core/models';
import { Icon } from '../shared/icon';
import { Kpi } from '../shared/kpi';
import { LineChart } from '../shared/line-chart';
import { PageHead } from '../shared/page-head';

export const METRICS_POLL_MS = 30000;
/** A coleta roda a cada 2 min; passou disto, os numeros estao velhos. */
export const STALE_S = 360;

type Cut = 'origem' | 'classe' | 'dia';

export const money = (x: number | null | undefined, d = 2): string =>
  x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + 'US$ ' + fmt(Math.abs(x), d);

const QUEM: Record<string, string> = { ia: 'IA', robo: 'robô e manuais' };

@Component({
  selector: 'app-observe',
  imports: [Kpi, PageHead, Icon, LineChart],
  styles: `
    .seg{display:inline-flex;border:1px solid var(--line-strong);border-radius:10px;overflow:hidden}
    .seg button{font:inherit;font-size:13px;font-weight:600;padding:6px 13px;border:none;background:transparent;color:var(--mute);cursor:pointer}
    .seg button.on{background:var(--accent-soft);color:var(--accent)}
    .prob{display:flex;align-items:flex-start;gap:10px}
    .prob app-icon{flex:none;margin-top:2px}
    .bar{height:6px;border-radius:99px;background:var(--accent);opacity:.7;margin-top:5px}`,
  template: `
    <app-page-head title="Observatório" subtitle="O que a corretora registrou, o que a IA fez e o que precisa de atenção">
      @if (m(); as m) {
        <span class="pill" [class.ok]="!stale()" [class.warn]="stale()"><span class="dot"></span>coleta há {{ dur(m.idade_s) }}</span>
      }
      <button class="btn" (click)="refresh()"><app-icon name="refresh" [size]="16" /> Atualizar</button>
    </app-page-head>

    @if (error()) { <div class="alert bad" role="alert"><app-icon name="alert" [size]="18" /> <span>Não consegui ler as métricas: {{ error() }}</span></div> }

    @if (m(); as m) {
      @if (stale()) {
        <div class="alert warn" role="alert"><app-icon name="alert" [size]="18" /> <span>Números parados há {{ dur(m.idade_s) }}: confira o serviço quant-metrics na VM.</span></div>
      }
      <section class="card">
        <div class="card-h"><h2>Precisa de atenção</h2>
          <span class="pill" [class]="worst()">{{ m.problemas.length ? m.problemas.length + ' item(ns)' : 'nada pendente' }}</span></div>
        <div class="list">
          @for (p of m.problemas; track p.texto) {
            <div class="prob"><app-icon name="alert" [size]="17" [class]="p.nivel" /><span>{{ p.texto }}</span></div>
          } @empty {
            <div class="prob"><app-icon name="check" [size]="17" class="ok" /><span>Serviços ativos, posições com stop e IA em dia.</span></div>
          }
        </div>
      </section>

      <div class="grid cols-4 mt">
        <app-kpi label="patrimônio demo" [value]="'US$ ' + fmt(m.conta.patrimonio)" [sub]="'saldo inicial implícito US$ ' + fmt(m.conta.inicial_implicito)" />
        <app-kpi label="resultado líquido" [value]="money(m.conta.liquido)" [tone]="tone(m.conta.liquido)" [sub]="'antes das taxas ' + money(m.conta.bruto)" />
        <app-kpi label="taxas pagas" [value]="'US$ ' + fmt(m.conta.taxas)" [sub]="m.conta.execucoes + ' execuções · funding ' + money(m.conta.funding)" />
        <app-kpi label="em aberto" [value]="money(m.conta.aberto)" [tone]="tone(m.conta.aberto)" [sub]="m.posicoes.length + ' posição(ões)'" />
      </div>

      <section class="card mt">
        <div class="card-h"><h2>Patrimônio</h2><span class="sub">um ponto a cada coleta</span></div>
        <app-line-chart [values]="equity()" [labels]="equityLabels()" [baseline]="m.conta.inicial_implicito" label="patrimônio da conta demo"
                        empty="o gráfico aparece depois de duas coletas" />
      </section>

      <section class="card mt">
        <div class="card-h">
          <h2>Onde ganha e onde perde</h2>
          <div class="seg" role="group" aria-label="agrupar por">
            <button [class.on]="cut() === 'origem'" (click)="cut.set('origem')">quem</button>
            <button [class.on]="cut() === 'classe'" (click)="cut.set('classe')">classe</button>
            <button [class.on]="cut() === 'dia'" (click)="cut.set('dia')">dia</button>
          </div>
        </div>
        <div class="scroll-x"><table>
          <thead><tr><th></th><th class="r">fechadas</th><th class="r">no lucro</th><th class="r">antes das taxas</th><th class="r">taxas</th><th class="r">líquido</th></tr></thead>
          <tbody>
            @for (g of groups(); track g.nome) {
              <tr><td>{{ name(g.nome) }}</td><td class="r">{{ g.fechadas }}</td><td class="r">{{ rate(g) }}</td>
                <td class="r">{{ money(g.bruto) }}</td><td class="r">{{ fmt(g.taxa) }}</td><td class="r" [class]="tone(g.liquido)">{{ money(g.liquido) }}</td></tr>
            } @empty { <tr><td colspan="6" class="sub">nenhuma execução ainda</td></tr> }
          </tbody>
        </table></div>
      </section>

      <div class="grid cols-2 mt">
        <section class="card">
          <div class="card-h"><h2>Posições abertas</h2></div>
          <div class="scroll-x"><table>
            <thead><tr><th>ativo</th><th>quem</th><th class="r">em aberto</th><th class="r">stop</th></tr></thead>
            <tbody>
              @for (p of m.posicoes; track p.asset) {
                <tr><td><b>{{ p.asset }}</b>&ngsp;<span class="faint">{{ p.qtd > 0 ? 'comprado' : 'vendido' }}</span></td><td>{{ name(p.quem) }}</td>
                  <td class="r" [class]="tone(p.aberto)">{{ money(p.aberto, 3) }}</td>
                  <td class="r"><span class="pill" [class.ok]="p.stop === true" [class.bad]="p.stop === false">{{ p.stop === true ? 'ativo' : p.stop === false ? 'SEM stop' : '?' }}</span></td></tr>
              } @empty { <tr><td colspan="4" class="sub">sem posição aberta</td></tr> }
            </tbody>
          </table></div>
        </section>
        <section class="card">
          <div class="card-h"><h2>Maiores resultados</h2><span class="sub">posições fechadas</span></div>
          <div class="scroll-x"><table>
            <tbody>
              @for (e of m.extremos; track e.asset + e.em) {
                <tr><td><b>{{ e.asset }}</b>&ngsp;<span class="faint">{{ name(e.quem) }}{{ e.corretora ? ' · saída da corretora' : '' }}</span></td>
                  <td class="sub">{{ when(e.em) }}</td><td class="r" [class]="tone(e.liquido)">{{ money(e.liquido) }}</td></tr>
              } @empty { <tr><td class="sub">nada fechado ainda</td></tr> }
            </tbody>
          </table></div>
        </section>
      </div>

      <div class="grid cols-2 mt">
        <section class="card">
          <div class="card-h"><h2>IA</h2>
            <span class="pill" [class.ok]="m.ia.ligada && !m.ia.sombra" [class.warn]="m.ia.sombra">{{ !m.ia.ligada ? 'desligada' : m.ia.sombra ? 'em sombra' : 'enviando ordens' }}</span></div>
          <p class="sub">{{ m.ia.modelo }} · a cada {{ m.ia.intervalo_min }} min · último ciclo há {{ dur(m.ia.ultimo_ciclo_s) }}</p>
          <p class="sub">24 h: {{ m.ia.ciclos_24h }} ciclos · {{ m.ia.erros_24h }} com erro · {{ m.ia.falhas_24h }} ordens falharam</p>
          @if (m.ia.ultima_analise) { <p class="note mt">{{ m.ia.ultima_analise }}</p> }
          @if (m.ia.recusas.length) {
            <h2 class="mt">Por que o código recusou (24 h)</h2>
            <div class="list mt">
              @for (r of m.ia.recusas; track r.motivo) {
                <div><div class="spread"><span class="sub">{{ r.motivo }}</span><b class="num">{{ r.n }}</b></div>
                  <div class="bar" [style.width.%]="share(r.n)"></div></div>
              }
            </div>
          }
        </section>
        <section class="card">
          <div class="card-h"><h2>Modo sombra</h2><span class="sub">simulado, nenhuma ordem enviada</span></div>
          @if (m.sombra.ciclos) {
            <p class="sub">{{ m.sombra.ciclos }} ciclos · {{ m.sombra.abertas }} aberturas · {{ m.sombra.fechadas }} fechadas · {{ m.sombra.ganhos }} no lucro</p>
            <p class="mt"><b class="num" [class]="tone(m.sombra.media_bps)">{{ m.sombra.media_bps == null ? 'sem resultado' : bps(m.sombra.media_bps) }}</b>
              <span class="sub"> líquido médio por posição simulada</span></p>
            @if (m.sombra.fechadas < 30) { <p class="note mt">Amostra pequena: com menos de 30 posições fechadas o número não diz nada.</p> }
            <table class="mt"><tbody>
              @for (s of m.sombra.ultimas; track s.asset + s.t) {
                <tr><td><b>{{ s.asset }}</b></td><td class="sub">{{ when(s.t) }}</td><td class="r" [class]="tone(s.bps)">{{ bps(s.bps) }}</td></tr>
              }
            </tbody></table>
          } @else { <div class="empty">a IA ainda não rodou em sombra</div> }
        </section>
      </div>

      <section class="card mt">
        <div class="card-h"><h2>Serviços na VM</h2></div>
        <div class="row">
          @for (s of m.servicos; track s.unit) {
            <span class="pill" [class]="s.estado === 'active' ? 'ok' : 'bad'" [title]="s.unit"><span class="dot"></span>{{ s.nome }}{{ s.estado === 'active' ? '' : ' · ' + s.estado }}</span>
          }
        </div>
        <p class="note mt">Registro local de trades: {{ money(m.registro.local) }} · corretora (fechadas e taxas): {{ money(m.registro.corretora) }} · diferença {{ money(m.registro.diferenca) }}.</p>
      </section>
    } @else if (!error()) {
      <div class="card"><div class="empty">
        @if (loading()) { carregando… } @else { <b>Sem coleta ainda</b>Ligue o quant-metrics.timer na VM; a primeira leitura sai em até 2 minutos. }
      </div></div>
    }`,
})
export class ObservePage {
  private readonly api = inject(ApiService);
  private readonly manual = new Subject<void>();

  protected readonly m = signal<Metrics | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly loading = signal(true);
  protected readonly cut = signal<Cut>('origem');

  protected readonly stale = computed(() => (this.m()?.idade_s ?? 0) > STALE_S);
  protected readonly worst = computed(() => {
    const p = this.m()?.problemas ?? [];
    return p.some(x => x.nivel === 'bad') ? 'bad' : p.length ? 'warn' : 'ok';
  });
  protected readonly groups = computed<MetricGroup[]>(() => {
    const m = this.m();
    return !m ? [] : this.cut() === 'origem' ? m.por_origem : this.cut() === 'classe' ? m.por_classe : m.por_dia;
  });
  protected readonly equity = computed(() => (this.m()?.equity ?? []).map(p => p[1]));
  protected readonly equityLabels = computed(() => (this.m()?.equity ?? []).map(p => this.when(p[0])));

  protected readonly fmt = fmt;
  protected readonly dur = dur;
  protected readonly tone = tone;
  protected readonly money = money;
  protected name = (k: string) => QUEM[k] ?? k;
  protected when = (s: number) => new Date(s * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  protected rate = (g: MetricGroup) => (g.fechadas ? `${g.ganhos} (${Math.round((100 * g.ganhos) / g.fechadas)}%)` : '—');
  protected bps = (x: number) => (x > 0 ? '+' : '') + fmt(x / 100, 2) + '%';
  protected share = (n: number) => (100 * n) / Math.max(1, ...(this.m()?.ia.recusas.map(r => r.n) ?? []));

  constructor() {
    merge(timer(0, METRICS_POLL_MS), this.manual).pipe(
      filter(() => typeof document === 'undefined' || !document.hidden),
      exhaustMap(() => this.api.metrics().pipe(
        catchError(e => { this.error.set(errMsg(e)); this.loading.set(false); return EMPTY; }))),
      takeUntilDestroyed(inject(DestroyRef)),
    ).subscribe(d => { this.m.set(d.disponivel ? d : null); this.error.set(null); this.loading.set(false); });
  }

  protected refresh(): void { this.manual.next(); }
}
