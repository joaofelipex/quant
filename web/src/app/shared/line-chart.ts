import { Component, computed, input } from '@angular/core';
import { buildChart, ChartLine } from '../core/chart';

@Component({
  selector: 'app-line-chart',
  template: `
    @if (model(); as m) {
      <svg [attr.viewBox]="'0 0 800 ' + height()" role="img" [attr.aria-label]="label()">
        @if (m.baseline != null) {
          <line x1="10" x2="790" [attr.y1]="m.baseline" [attr.y2]="m.baseline" stroke="var(--line)" />
        }
        <polyline [attr.points]="m.points" fill="none" stroke="var(--accent)" stroke-width="1.7" />
        @for (l of m.lines; track l.label) {
          <line x1="10" x2="790" [attr.y1]="l.y" [attr.y2]="l.y" [attr.stroke]="l.color" stroke-dasharray="5 4" />
          <text x="14" [attr.y]="l.y - 4" [attr.fill]="l.color" font-size="11">{{ l.label }}</text>
        }
      </svg>
    } @else {
      <div class="s">{{ empty() }}</div>
    }`,
})
export class LineChart {
  readonly values = input.required<number[]>();
  readonly height = input(220);
  readonly lines = input<ChartLine[]>([]);
  readonly baseline = input<number | undefined>(undefined);
  readonly label = input('gráfico');
  readonly empty = input('sem dados para o gráfico');
  protected readonly model = computed(() =>
    buildChart(this.values(), this.height(), { lines: this.lines(), baseline: this.baseline() }));
}
