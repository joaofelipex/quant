import { Injectable, effect, signal } from '@angular/core';

export type Theme = 'dark' | 'light';
const KEY = 'quant-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<Theme>(this.initial());

  constructor() {
    effect(() => {
      const t = this.theme();
      document.documentElement.dataset['theme'] = t;
      try { localStorage.setItem(KEY, t); } catch { /* navegacao privada: so nao persiste */ }
    });
  }

  toggle(): void { this.theme.update(t => (t === 'dark' ? 'light' : 'dark')); }

  private initial(): Theme {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === 'dark' || saved === 'light') return saved;
    } catch { /* ignora */ }
    return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
}
