import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, of, tap } from 'rxjs';
import { CONTROL_HEADERS } from './api.service';

export interface LoginForm { user: string; password: string; lembrar: boolean }

/** Sessao do painel: o cookie e HttpOnly (o JS nem ve), entao so perguntamos ao servidor quem somos. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly user = signal<string | null>(null);
  /** false ate a primeira resposta de api/session (evita piscar a tela de login a cada F5). */
  readonly checked = signal(false);
  /** false = o servidor ainda nao tem senha definida (falha fechada). */
  readonly configured = signal(true);

  check(): void {
    this.http.get<{ user: string }>('api/session').pipe(
      catchError((e: HttpErrorResponse) => {
        this.configured.set((e.error as { configurado?: boolean } | null)?.configurado !== false);
        return of(null);
      }),
    ).subscribe(r => { this.user.set(r?.user ?? null); this.checked.set(true); });
  }

  login(f: LoginForm): Observable<{ user: string }> {
    return this.http.post<{ user: string }>('api/login', f, { headers: CONTROL_HEADERS }).pipe(
      tap(r => { this.user.set(r.user); this.checked.set(true); }));
  }

  logout(): void {
    this.http.post('api/logout', {}, { headers: CONTROL_HEADERS }).subscribe({ complete: () => this.expire(), error: () => this.expire() });
  }

  changePassword(atual: string, nova: string): Observable<unknown> {
    return this.http.post('api/password', { atual, nova }, { headers: CONTROL_HEADERS }).pipe(tap(() => this.expire()));
  }

  /** Sessao acabou (logout, troca de senha ou 401 do servidor): volta para a tela de login. */
  expire(): void { this.user.set(null); }
}

/** 401 em qualquer chamada (menos o proprio login) = sessao expirou: mostra o login em vez de erros soltos. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  return next(req).pipe(tap({
    error: e => {
      if (e instanceof HttpErrorResponse && e.status === 401 && !req.url.endsWith('api/login') && !req.url.endsWith('api/session')) auth.expire();
    },
  }));
};
