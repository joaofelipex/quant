import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AccountsService } from './accounts.service';
import { AuthService, Me, authInterceptor } from './auth.service';

const ME = (role: Me['role'] = 'admin'): Me => ({ id: 'a1', user: 'chefe', role, sid: 's', totp: false });

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()] });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  it('check: sessao valida preenche usuario e papel', () => {
    auth.check();
    http.expectOne('api/session').flush({ user: ME('operador'), setup: false });
    expect(auth.user()).toBe('chefe');
    expect(auth.canOperate()).toBe(true);
    expect(auth.isAdmin()).toBe(false);
    expect(auth.checked()).toBe(true);
  });

  it('check: sem sessao e sem usuarios cadastrados mostra o primeiro acesso', () => {
    auth.check();
    http.expectOne('api/session').flush({ user: null, setup: true });
    expect(auth.me()).toBeNull();
    expect(auth.setup()).toBe(true);
  });

  it('leitor nao opera nem administra', () => {
    auth.me.set(ME('leitor'));
    expect(auth.canOperate()).toBe(false);
    expect(auth.isAdmin()).toBe(false);
  });

  it('login envia o cabecalho CSRF, o codigo 2FA e guarda o usuario', () => {
    auth.login({ user: 'chefe', password: 'x', lembrar: true, code: '123456' }).subscribe();
    const req = http.expectOne('api/login');
    expect(req.request.headers.get('X-Quant-Control')).toBe('1');
    expect(req.request.body).toEqual({ user: 'chefe', password: 'x', lembrar: true, code: '123456' });
    req.flush({ user: ME() });
    expect(auth.user()).toBe('chefe');
    http.expectOne('api/session').flush({ user: ME(), setup: false });  // confirma a sessao completa
  });

  it('primeiro acesso manda o token e desliga o modo setup', () => {
    auth.setup.set(true);
    auth.firstAccess('tok', 'chefe', 'senha-longa-123').subscribe();
    const req = http.expectOne('api/setup');
    expect(req.request.body).toEqual({ token: 'tok', user: 'chefe', password: 'senha-longa-123' });
    req.flush({ user: ME() });
    expect(auth.setup()).toBe(false);
    http.expectOne('api/session').flush({ user: ME(), setup: false });
  });

  it('401 em qualquer chamada derruba a sessao, menos nas de entrada', () => {
    auth.me.set(ME());
    TestBed.inject(HttpClient).post('api/login', {}).subscribe({ error: () => {} });
    http.expectOne('api/login').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.user()).toBe('chefe');
    TestBed.inject(HttpClient).get('api/status').subscribe({ error: () => {} });
    http.expectOne('api/status').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.user()).toBeNull();
  });

  it('logout limpa a sessao', () => {
    auth.me.set(ME());
    auth.logout();
    http.expectOne('api/logout').flush({});
    expect(auth.user()).toBeNull();
  });

  it('troca de senha pelo servico de contas derruba a sessao local', () => {
    auth.me.set(ME());
    TestBed.inject(AccountsService).changePassword('a', 'b').subscribe();
    http.expectOne('api/password').flush({ ok: true });
    expect(auth.user()).toBeNull();
  });
});
