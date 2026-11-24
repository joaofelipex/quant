import { Component, computed, inject } from '@angular/core';
import { ChartLine } from '../core/chart';
import { dur, fmt, hhmm, pct, TIMEFRAME_S, tone } from '../core/format';
import { Tone } from '../core/models';
import { StatusStore } from '../core/status.store';
import { LineChart } from '../shared/line-chart';
import { StatCard } from '../shared/stat-card';

const MODE_NOTE: Record<string, string> = {
  paper: 'simulado, sem ordens reais', testnet: 'ambiente de teste da corretora', live: 'ATENÇÃO: conta real',
};

@Component({
  selector: 'app-overview',
  imports: [StatCard, LineChart],
  template: `
    @if (d(); as d) {
      <h2>Runner</h2>
      <div class="grid">
        <app-stat label="serviço" [value]="d.service" [tone]="active() ? 'ok' : 'bad'"
                  [sub]="'ativo há ' + dur(d.health.uptime_s) + ' · ' + (d.health.restarts ?? '—') + ' reinício(s) · ' + (d.health.memory_mb ?? '—') + ' MB'" />
        <app-stat label="modo · corretora" [value]="(cfg()['QUANT_MODE'] || '—') + ' · ' + (cfg()['QUANT_VENUE'] || 'binance')"
                  [tone]="cfg()['QUANT_MODE'] === 'paper' ? '' : 'warn'" [sub]="modeNote()" />
        <app-stat label="símbolo · timeframe" [value]="cfg()['QUANT_SYMBOL'] || '—'"
                  [sub]="'timeframe ' + (cfg()['QUANT_TIMEFRAME'] || '—') + ' · qty ' + (cfg()['QUANT_QTY'] || '—') + ' · perda máx/dia ' + (cfg()['QUANT_MAX_DAILY_LOSS'] || '—')" />
        <app-stat label="última barra processada" [value]="d.state?.last_bar || '—'" [tone]="stale() && active() ? 'warn' : ''"
                  [sub]="d.last_bar_age_s == null ? '' : 'há ' + dur(d.last_bar_age_s)" />
      </div>

      <h2>Posição e risco</h2>
      <div class="grid">
        <app-stat label="posição" [value]="position()" />
        <app-stat label="entrada · stop" [value]="entryStop()" />
        <app-stat label="PnL do dia · trades" [value]="fmt(pnlDay()) + ' · ' + (risk().trades ?? 0)" [tone]="pnlTone()" />
        <app-stat label="trava de risco" [value]="risk().halted ? 'TRAVADO' + (risk().reason ? ': ' + risk().reason : '') : 'livre'"
                  [tone]="risk().halted ? 'bad' : 'ok'" />
      </div>

      <h2>Preço recente · entrada e stop</h2>
      <div class="card">
        <app-line-chart [values]="prices()" [lines]="refLines()" label="preço recente" empty="sem barras (feed público indisponível)" />
        <div class="s">{{ chartNote() }}</div>
      </div>
    }`,
})
export class OverviewPage {
  private readonly store = inject(StatusStore);
  protected readonly d = this.store.data;
  protected readonly dur = dur;
  protected readonly fmt = fmt;

  protected readonly cfg = computed(() => this.d()?.config ?? {});
  protected readonly risk = computed(() => this.d()?.state?.risk ?? {});
  protected readonly active = computed(() => this.d()?.service === 'active');
  protected readonly modeNote = computed(() => MODE_NOTE[this.cfg()['QUANT_MODE']] ?? '');
  protected readonly stale = computed(() => {
    const age = this.d()?.last_bar_age_s;
    return age != null && age > (TIMEFRAME_S[this.cfg()['QUANT_TIMEFRAME']] ?? 60) * 3;
  });
  protected readonly position = computed(() => {
    const p = this.d()?.state?.executor?.pos;
    return p ? JSON.stringify(p).replace(/[{}"]/g, '') : 'sem posição';
  });
  protected readonly entry = computed(() => this.d()?.state?.entry?.price ?? null);
  protected readonly stop = computed(() => this.d()?.state?.stop ?? null);
  protected readonly entryStop = computed(() =>
    this.entry() == null ? '—' : `${fmt(this.entry())} · ${this.stop() != null ? fmt(this.stop()) : 'sem stop'}`);
  protected readonly pnlDay = computed(() => Number(this.risk().pnl ?? 0));
  protected readonly pnlTone = computed<Tone>(() => tone(this.pnlDay()));

  protected readonly prices = computed(() => (this.d()?.bars ?? []).map(b => b[1]));
  protected readonly refLines = computed<ChartLine[]>(() => {
    const out: ChartLine[] = [];
    if (this.entry() != null) out.push({ value: this.entry()!, color: 'var(--ok)', label: `entrada ${fmt(this.entry())}` });
    if (this.stop() != null) out.push({ value: this.stop()!, color: 'var(--bad)', label: `stop ${fmt(this.stop())}` });
    return out;
  });
  protected readonly chartNote = computed(() => {
    const bars = this.d()?.bars ?? [];
    if (bars.length < 2) return '';
    const ys = bars.map(b => b[1]);
    const first = ys[0], last = ys[ys.length - 1];
    return `${hhmm(bars[0][0])} → ${hhmm(bars[bars.length - 1][0])} · último ${fmt(last)} (${pct(last / first - 1)} na janela) · mín ${fmt(Math.min(...ys))} · máx ${fmt(Math.max(...ys))}`;
  });
}
