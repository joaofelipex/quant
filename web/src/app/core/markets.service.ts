import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';

export interface Market { id: string; ticker: string; title: string; cls: string; label: string; binance: boolean }

/** Catalogo dos perpetuos operaveis (acoes, cripto, cambio, metais, indices...), vindo do servidor uma vez. */
@Injectable({ providedIn: 'root' })
export class MarketsService {
  private readonly http = inject(HttpClient);
  readonly markets = signal<Market[]>([]);
  readonly binance = signal<string[]>([]);
  readonly ids = computed(() => this.markets().map(m => m.id));
  /** Classes na ordem do catalogo, cada uma com seus mercados. */
  readonly groups = computed(() => {
    const out = new Map<string, { label: string; items: Market[] }>();
    for (const m of this.markets()) {
      const g = out.get(m.cls) ?? { label: m.label, items: [] };
      g.items.push(m);
      out.set(m.cls, g);
    }
    return [...out.entries()].map(([cls, g]) => ({ cls, ...g }));
  });
  private loaded = false;

  load(): void {
    if (this.loaded) return;
    this.loaded = true;
    this.http.get<{ markets: Market[]; binance: string[] }>('api/markets').subscribe({
      next: r => { this.markets.set(r.markets); this.binance.set(r.binance); },
      error: () => { this.loaded = false; },
    });
  }

  title(id: string): string { return this.markets().find(m => m.id === id)?.title ?? id; }
}
