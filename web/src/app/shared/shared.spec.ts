import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';
import { ThemeService } from '../core/theme.service';
import { ConfirmHost, ConfirmService } from './confirm';
import { ToastService } from './toast';

describe('ToastService', () => {
  it('empilha, limita a 4 e descarta', () => {
    const t = TestBed.inject(ToastService);
    for (let i = 0; i < 6; i++) t.show(`m${i}`, '', 0);
    expect(t.items().length).toBe(4);
    expect(t.items()[3].text).toBe('m5');
    t.dismiss(t.items()[0].id);
    expect(t.items().length).toBe(3);
  });

  it('some sozinho depois do prazo', () => {
    vi.useFakeTimers();
    const t = TestBed.inject(ToastService);
    t.show('x', 'ok', 1000);
    expect(t.items().length).toBe(1);
    vi.advanceTimersByTime(1100);
    expect(t.items().length).toBe(0);
    vi.useRealTimers();
  });
});

describe('ThemeService', () => {
  it('alterna e aplica no <html>', () => {
    const th = TestBed.inject(ThemeService);
    const before = th.theme();
    th.toggle();
    TestBed.tick();
    expect(th.theme()).not.toBe(before);
    expect(document.documentElement.dataset['theme']).toBe(th.theme());
  });
});

describe('ConfirmService', () => {
  it('acao com texto exigido so confirma depois de digitar', async () => {
    const f = TestBed.createComponent(ConfirmHost);
    const svc = TestBed.inject(ConfirmService);
    const answer = svc.ask({ title: 'Kill?', requireText: 'KILL', danger: true });
    f.detectChanges();
    await f.whenStable();
    const submit = f.nativeElement.querySelector('button[type=submit]') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    const input = f.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = 'KILL';
    input.dispatchEvent(new Event('input'));
    f.detectChanges();
    await f.whenStable();
    f.detectChanges();
    expect(submit.disabled).toBe(false);
    submit.click();
    expect(await answer).toBe(true);
  });

  it('cancelar resolve falso', async () => {
    const f = TestBed.createComponent(ConfirmHost);
    const svc = TestBed.inject(ConfirmService);
    const answer = svc.ask({ title: 'Parar?' });
    f.detectChanges();
    (f.nativeElement.querySelector('button[type=button]') as HTMLButtonElement).click();
    expect(await answer).toBe(false);
  });
});
