import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Subject, catchError, exhaustMap, filter, merge, timer } from 'rxjs';
import { ApiService, errMsg } from './api.service';
import { AuthService } from './auth.service';
import { dur, TIMEFRAME_S } from './format';
import { Status, Tone } from './models';

export interface Banner { text: string; tone: Tone }

export const POLL_MS = 5000;

/** Estado de saude do runner resumido numa frase (a mesma regra do painel antigo). */
export function computeBanner(d: Status | null, error: string | null): Banner {
  if (error && !d) return { text: `sem resposta do serviço de controle (${error})`, tone: 'bad' };
  if (error) return { text: 'sem resposta do serviço de controle: os dados abaixo podem estar desatualizados', tone: 'bad' };
  if (!d) return { text: 'carregando…', tone: '' };
  const risk = d.state?.risk ?? {};
  const active = d.service === 'active';
  const tf = TIMEFRAME_S[d.config['QUANT_TIMEFRAME']] ?? 60;
  const stale = d.last_bar_age_s != null && d.last_bar_age_s > tf * 3;
  if (d.kill_file) return { text: 'KILL acionado: o runner está parado ou parando', tone: 'bad' };
  if (!active) return { text: 'runner não está ativo', tone: 'bad' };
  if (risk.halted) return { text: 'runner ativo, mas com a trava de risco ligada', tone: 'warn' };
  if (stale) return { text: `runner ativo, mas sem barra nova há ${dur(d.last_bar_age_s)}`, tone: 'warn' };
  return { text: 'runner ativo e dentro do normal', tone: 'ok' };
}

/** Fonte unica do /api/status: consulta a cada 5 s (so com a aba visivel) e expoe sinais para as paginas. */
@Injectable({ providedIn: 'root' })
export class StatusStore {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly manual = new Subject<void>();

  readonly data = signal<Status | null>(null);
  readonly error = signal<string | null>(null);
  readonly loading = signal(true);
  readonly banner = computed(() => computeBanner(this.data(), this.error()));
  readonly connected = computed(() => this.error() == null && this.data() != null);

  constructor() {
    merge(timer(0, POLL_MS), this.manual).pipe(
      filter(() => this.auth.user() != null && (typeof document === 'undefined' || !document.hidden)),
      exhaustMap(() => this.api.status().pipe(
        catchError(e => { this.error.set(errMsg(e)); this.loading.set(false); return EMPTY; }))),
      takeUntilDestroyed(inject(DestroyRef)),
    ).subscribe(d => { this.data.set(d); this.error.set(null); this.loading.set(false); });
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => { if (!document.hidden) this.refresh(); });
    }
  }

  refresh(): void { this.manual.next(); }
}
