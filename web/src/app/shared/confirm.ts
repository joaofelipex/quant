import { Component, ElementRef, Injectable, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Icon } from './icon';

export interface ConfirmOptions {
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
  /** Se informado, o botao so habilita depois de digitar exatamente este texto (acoes irreversiveis). */
  requireText?: string;
}
interface Pending extends ConfirmOptions { resolve: (ok: boolean) => void }

/** Dialogo de confirmacao proprio (usa <dialog> nativo: foco preso, ESC fecha), no lugar do window.confirm. */
@Injectable({ providedIn: 'root' })
export class ConfirmService {
  readonly pending = signal<Pending | null>(null);
  ask(opts: ConfirmOptions): Promise<boolean> {
    return new Promise(resolve => this.pending.set({ ...opts, resolve }));
  }
}

@Component({
  selector: 'app-confirm',
  imports: [FormsModule, Icon],
  template: `
    <dialog #dlg (close)="finish(false)" (click)="backdrop($event)">
      @if (svc.pending(); as p) {
        <form class="box" (submit)="$event.preventDefault(); finish(true)">
          <div class="head" [class.danger]="p.danger"><app-icon [name]="p.danger ? 'alert' : 'shield'" [size]="20" /><h2>{{ p.title }}</h2></div>
          @if (p.body) { <p class="body">{{ p.body }}</p> }
          @if (p.requireText) {
            <label class="field"><span>Digite <code>{{ p.requireText }}</code> para confirmar</span>
              <input autocomplete="off" [ngModel]="typed()" (ngModelChange)="typed.set($event)" name="typed"></label>
          }
          <div class="actions">
            <button type="button" class="btn ghost" (click)="finish(false)">Cancelar</button>
            <button type="submit" class="btn" [class.danger]="p.danger" [class.primary]="!p.danger"
                    [disabled]="!!p.requireText && typed() !== p.requireText">{{ p.confirmLabel ?? 'Confirmar' }}</button>
          </div>
        </form>
      }
    </dialog>`,
  styles: `
    dialog{border:1px solid var(--line-strong);border-radius:16px;background:var(--surface);color:var(--ink);padding:0;width:min(440px,calc(100vw - 32px));box-shadow:0 24px 60px rgba(0,0,0,.45)}
    dialog::backdrop{background:rgba(5,8,14,.62);backdrop-filter:blur(2px)}
    .box{display:flex;flex-direction:column;gap:14px;padding:22px}
    .head{display:flex;align-items:center;gap:10px}.head.danger{color:var(--bad)}
    .body{color:var(--mute);font-size:14px;white-space:pre-line}
    .actions{display:flex;justify-content:flex-end;gap:8px;margin-top:4px}`,
})
export class ConfirmHost {
  protected readonly svc = inject(ConfirmService);
  protected readonly typed = signal('');
  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');

  constructor() {
    effect(() => {
      const el = this.dlg().nativeElement;
      if (this.svc.pending() && !el.open) {
        this.typed.set('');
        if (typeof el.showModal === 'function') el.showModal(); else el.setAttribute('open', '');  // jsdom nao tem showModal
      }
    });
  }

  protected finish(ok: boolean): void {
    const p = this.svc.pending();
    if (!p) return;
    this.svc.pending.set(null);
    const el = this.dlg().nativeElement;
    if (el.open) { if (typeof el.close === 'function') el.close(); else el.removeAttribute('open'); }
    p.resolve(ok);
  }

  protected backdrop(e: MouseEvent): void {
    if (e.target === this.dlg().nativeElement) this.finish(false);
  }
}
