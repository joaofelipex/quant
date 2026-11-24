import { Component, computed, ElementRef, inject, input, signal } from '@angular/core';
import { ChartLine, CHART_W, buildChart } from '../core/chart';
import { fmt } from '../core/format';

let uid = 0;

@Component({
  selector: 'app-line-chart',
  template: `
    @if (model(); as m) {
      <svg [attr.viewBox]="'0 0 ' + W + ' ' + height()" role="img" [attr.aria-label]="label()"
           (pointermove)="move($event, m.xs)" (pointerleave)="hover.set(null)" (pointerdown)="move($event, m.xs)">
        <defs>
          <linearGradient [attr.id]="gid" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="var(--accent)" stop-opacity=".28" />
            <stop offset="1" stop-color="var(--accent)" stop-opacity="0" />
          </linearGradient>
        </defs>
        @if (m.baseline != null) {
          <line x1="10" x2="790" [attr.y1]="m.baseline" [attr.y2]="m.baseline" stroke="var(--line-strong)" stroke-dasharray="2 4" />
        }
        <path [attr.d]="m.area" [attr.fill]="'url(#' + gid + ')'" />
        <polyline [attr.points]="m.points" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        @for (l of m.lines; track l.label) {
          <line x1="10" x2="790" [attr.y1]="l.y" [attr.y2]="l.y" [attr.stroke]="l.color" stroke-dasharray="6 5" stroke-width="1.4" />
          <text x="792" [attr.y]="l.y - 5" text-anchor="end" [attr.fill]="l.color" font-size="12" font-weight="600">{{ l.label }}</text>
        }
        <text x="14" y="14" fill="var(--faint)" font-size="11">máx {{ format()(m.hi) }}</text>
        <text x="14" [attr.y]="height() - 5" fill="var(--faint)" font-size="11">mín {{ format()(m.lo) }}</text>
        @if (hover(); as i) {
          <line [attr.x1]="m.xs[i]" [attr.x2]="m.xs[i]" y1="0" [attr.y2]="height()" stroke="var(--faint)" stroke-dasharray="3 3" />
          <circle [attr.cx]="m.xs[i]" [attr.cy]="m.ys[i]" r="4.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" />
          <g [attr.transform]="'translate(' + tipX(m.xs[i]) + ',' + tipY(m.ys[i]) + ')'">
            <rect width="132" height="42" rx="8" fill="var(--surface-2)" stroke="var(--line-strong)" />
            <text x="10" y="18" fill="var(--ink)" font-size="14" font-weight="650">{{ format()(m.values[i]) }}</text>
            <text x="10" y="34" fill="var(--mute)" font-size="11.5">{{ tipLabel(i) }}</text>
          </g>
        }
      </svg>
    } @else {
      <div class="empty">{{ empty() }}</div>
    }`,
  styles: `svg{display:block;width:100%;height:auto;touch-action:pan-y;cursor:crosshair}`,
})
export class LineChart {
  protected readonly W = CHART_W;
  protected readonly gid = `lc${++uid}`;
  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly values = input.required<number[]>();
  /** Rotulos do eixo x (um por ponto), mostrados no tooltip. */
  readonly labels = input<string[]>([]);
  readonly height = input(240);
  readonly lines = input<ChartLine[]>([]);
  readonly baseline = input<number | undefined>(undefined);
  readonly label = input('gráfico');
  readonly empty = input('sem dados para o gráfico');
  readonly format = input<(v: number) => string>((v: number) => fmt(v));

  protected readonly hover = signal<number | null>(null);
  protected readonly model = computed(() =>
    buildChart(this.values(), this.height(), { lines: this.lines(), baseline: this.baseline() }));

  protected tipLabel = (i: number) => this.labels()[i] ?? `ponto ${i + 1}`;
  protected tipX = (x: number) => (x > 560 ? x - 142 : x + 10);
  protected tipY = (y: number) => Math.min(Math.max(y - 21, 6), this.height() - 48);

  protected move(e: PointerEvent, xs: number[]): void {
    const svg = this.el.nativeElement.querySelector('svg');
    if (!svg) return;
    const box = svg.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * CHART_W;
    let best = 0;
    for (let i = 1; i < xs.length; i++) if (Math.abs(xs[i] - x) < Math.abs(xs[best] - x)) best = i;
    this.hover.set(best);
  }
}
