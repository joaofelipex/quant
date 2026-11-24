import { Component, Injectable, inject, signal } from '@angular/core';
import { Icon } from './icon';
import { Tone } from '../core/models';

export interface ToastItem { id: number; text: string; tone: Tone }

/** Avisos curtos e nao bloqueantes (substituem as mensagens soltas no rodape dos formularios). */
@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly items = signal<ToastItem[]>([]);
  private seq = 0;

  show(text: string, tone: Tone = '', ms = 5000): void {
    const id = ++this.seq;
    this.items.update(l => [...l.slice(-3), { id, text, tone }]);
    if (ms > 0) setTimeout(() => this.dismiss(id), tone === 'bad' ? ms * 2 : ms);
  }
  ok(text: string): void { this.show(text, 'ok'); }
  error(text: string): void { this.show(text, 'bad'); }
  dismiss(id: number): void { this.items.update(l => l.filter(t => t.id !== id)); }
}

@Component({
  selector: 'app-toasts',
  imports: [Icon],
  template: `
    <div class="host" role="status" aria-live="polite">
      @for (t of svc.items(); track t.id) {
        <div class="toast" [class]="t.tone">
          <app-icon [name]="t.tone === 'bad' ? 'alert' : t.tone === 'ok' ? 'check' : 'bell'" [size]="16" />
          <span>{{ t.text }}</span>
          <button class="x" (click)="svc.dismiss(t.id)" aria-label="fechar"><app-icon name="x" [size]="14" /></button>
        </div>
      }
    </div>`,
  styles: `
    .host{position:fixed;right:16px;bottom:16px;z-index:50;display:flex;flex-direction:column;gap:8px;max-width:min(420px,calc(100vw - 32px))}
    @media(max-width:760px){.host{bottom:76px}}
    .toast{display:flex;gap:10px;align-items:flex-start;background:var(--surface);border:1px solid var(--line-strong);border-left:3px solid var(--accent);
      border-radius:10px;padding:10px 12px;box-shadow:var(--shadow);font-size:14px;animation:in .18s ease-out}
    .toast.ok{border-left-color:var(--ok)}.toast.bad{border-left-color:var(--bad)}.toast.warn{border-left-color:var(--warn)}
    .toast app-icon{margin-top:2px}.toast.ok app-icon{color:var(--ok)}.toast.bad app-icon{color:var(--bad)}
    .x{margin-left:auto;background:none;border:none;color:var(--mute);cursor:pointer;padding:2px;line-height:0}
    @keyframes in{from{opacity:0;transform:translateY(6px)}}`,
})
export class Toasts { protected readonly svc = inject(ToastService); }
