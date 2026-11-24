import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, of, tap } from 'rxjs';
import { CONTROL_HEADERS } from './api.service';

export type Role = 'leitor' | 'operador' | 'admin';
export const ROLE_LABEL: Record<Role, string> = { leitor: 'leitor (só vê)', operador: 'operador', admin: 'administrador' };

export interface Me { id: string; user: string; role: Role; sid: string; totp: boolean }
export interface LoginForm { user: string; password: string; lembrar: boolean; code?: string }

const AUTH_PATHS = ['api/login', 'api/session', 'api/setup', 'api/logout'];

/** Sessao do painel: o cookie e HttpOnly (o JS nem ve), entao so perguntamos ao servidor quem somos. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly me = signal<Me | null>(null);
  readonly user = computed(() => this.me()?.user ?? null);
  readonly role = computed<Role | null>(() => this.me()?.role ?? null);
  readonly isAdmin = computed(() => this.role() === 'admin');
  readonly canOperate = computed(() => this.role() === 'admin' || this.role() === 'operador');
  /** false ate a primeira resposta de api/session (evita piscar a tela de login a cada F5). */
  readonly checked = signal(false);
  /** true = ainda nao ha nenhum usuario: mostra a tela de primeiro acesso. */
  readonly setup = signal(false);

  check(): void {
    this.http.get<{ user: Me | null; setup: boolean }>('api/session').pipe(
      catchError(() => of({ user: null, setup: false })),
    ).subscribe(r => { this.me.set(r.user); this.setup.set(r.setup); this.checked.set(true); });
  }

  login(f: LoginForm): Observable<{ user: Me }> {
    return this.http.post<{ user: Me }>('api/login', f, { headers: CONTROL_HEADERS }).pipe(tap(r => this.enter(r.user)));
  }

  firstAccess(user: string, password: string): Observable<{ user: Me }> {
    return this.http.post<{ user: Me }>('api/setup', { user, password }, { headers: CONTROL_HEADERS }).pipe(
      tap(r => { this.setup.set(false); this.enter(r.user); }));
  }

  logout(): void {
    this.http.post('api/logout', {}, { headers: CONTROL_HEADERS }).subscribe({ complete: () => this.expire(), error: () => this.expire() });
  }

  /** Sessao nova aceita. O refresh da sessao completa (sid, totp) vem do servidor. */
  private enter(u: Me): void { this.me.set(u); this.checked.set(true); this.check(); }

  /** Sessao acabou (logout, troca de senha ou 401 do servidor): volta para a tela de login. */
  expire(): void { this.me.set(null); }
}

/** 401 em qualquer chamada (menos as de entrada) = sessao expirou: mostra o login em vez de erros soltos. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  return next(req).pipe(tap({
    error: e => {
      if (e instanceof HttpErrorResponse && e.status === 401 && !AUTH_PATHS.some(p => req.url.endsWith(p))) auth.expire();
    },
  }));
};
