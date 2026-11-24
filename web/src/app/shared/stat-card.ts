import { Component, input } from '@angular/core';
import { Tone } from '../core/models';

@Component({
  selector: 'app-stat',
  template: `
    <div class="card">
      <div class="k">{{ label() }}</div>
      <div class="v" [class]="tone()">{{ value() }}</div>
      @if (sub()) { <div class="s">{{ sub() }}</div> }
    </div>`,
})
export class StatCard {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly sub = input<string>('');
  readonly tone = input<Tone>('');
}
