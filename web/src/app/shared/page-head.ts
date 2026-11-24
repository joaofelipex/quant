import { Component, input } from '@angular/core';

@Component({
  selector: 'app-page-head',
  template: `
    <header class="head">
      <div>
        <h1>{{ title() }}</h1>
        @if (subtitle()) { <p class="sub">{{ subtitle() }}</p> }
      </div>
      <div class="row"><ng-content /></div>
    </header>`,
  styles: `.head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin:4px 0 20px}`,
})
export class PageHead {
  readonly title = input.required<string>();
  readonly subtitle = input<string>('');
}
