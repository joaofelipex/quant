import { Component, input } from '@angular/core';
import { Tone } from '../core/models';

/** Indicador: rotulo discreto, valor grande, detalhe opcional. */
@Component({
  selector: 'app-kpi',
  template: `
    <div class="card kpi">
      <div class="k">{{ label() }}</div>
      <div class="v num" [class]="tone()">{{ value() }}</div>
      @if (sub()) { <div class="s">{{ sub() }}</div> }
    </div>`,
  styles: `
    .kpi{height:100%;display:flex;flex-direction:column;gap:2px;padding:16px 18px}
    .k{font-size:12px;font-weight:600;color:var(--faint);text-transform:uppercase;letter-spacing:.06em}
    .v{font-size:26px;font-weight:650;letter-spacing:-.02em;line-height:1.25;word-break:break-word}
    .s{font-size:12.5px;color:var(--mute)}
    @media(max-width:640px){.kpi{padding:12px 13px}.v{font-size:21px}.k{font-size:11px}}`,
})
export class Kpi {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly sub = input<string>('');
  readonly tone = input<Tone>('');
}
