import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';
import { AuthService, authInterceptor } from './auth.service';

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()] });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  it('check: sessao valida preenche o usuario', () => {
    auth.check();
    http.expectOne('api/session').flush({ user: 'painel' });
    expect(auth.user()).toBe('painel');
    expect(auth.checked()).toBe(true);
  });

  it('check: 401 deixa deslogado e sinaliza senha nao definida', () => {
    auth.check();
    http.expectOne('api/session').flush({ erro: 'login necessario', configurado: false }, { status: 401, statusText: 'Unauthorized' });
    expect(auth.user()).toBeNull();
    expect(auth.checked()).toBe(true);
    expect(auth.configured()).toBe(false);
  });

  it('login envia o cabecalho CSRF e guarda o usuario', () => {
    auth.login({ user: 'painel', password: 'x', lembrar: true }).subscribe();
    const req = http.expectOne('api/login');
    expect(req.request.headers.get('X-Quant-Control')).toBe('1');
    expect(req.request.body).toEqual({ user: 'painel', password: 'x', lembrar: true });
    req.flush({ user: 'painel' });
    expect(auth.user()).toBe('painel');
  });

  it('401 em qualquer chamada derruba a sessao, menos no proprio login', () => {
    auth.user.set('painel');
    TestBed.inject(HttpClient).post('api/login', {}).subscribe({ error: () => {} });
    http.expectOne('api/login').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.user()).toBe('painel');
    TestBed.inject(HttpClient).get('api/status').subscribe({ error: () => {} });
    http.expectOne('api/status').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.user()).toBeNull();
  });

  it('logout e troca de senha limpam a sessao', () => {
    auth.user.set('painel');
    auth.logout();
    http.expectOne('api/logout').flush({});
    expect(auth.user()).toBeNull();
    auth.user.set('painel');
    auth.changePassword('a', 'b').subscribe();
    http.expectOne('api/password').flush({ ok: true });
    expect(auth.user()).toBeNull();
  });
});
