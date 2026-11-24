import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { AuthService, Me } from '../core/auth.service';
import { StatusStore } from '../core/status.store';
import { AccountPage } from './account.page';
import { LoginPage } from './login.page';
import { OperatePage } from './operate.page';
import { UsersPage } from './users.page';

const me = (role: Me['role']): Me => ({ id: 'a1', user: 'chefe', role, sid: 's', totp: false });

function setup(page: Type<unknown>, role: Me['role'] | null, first = false): HTMLElement {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
      { provide: StatusStore, useValue: { data: signal(null), banner: signal({ text: 'x', tone: 'ok' }), refresh: () => {} } }],
  });
  const auth = TestBed.inject(AuthService);
  auth.me.set(role ? me(role) : null);
  auth.setup.set(first);
  const f = TestBed.createComponent(page);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('telas de conta', () => {
  it('login normal', () => {
    const t = setup(LoginPage, null).textContent!;
    expect(t).toContain('Entrar');
    expect(t).toContain('manter conectado');
    expect(t).not.toContain('Repita a senha');
  });

  it('primeiro acesso pede so usuario e senha repetida', () => {
    const t = setup(LoginPage, null, true).textContent!;
    expect(t).toContain('Crie a conta de administrador');
    expect(t).toContain('Repita a senha');
    expect(t).not.toContain('Token');
  });

  it('conta: senha, 2FA e sessoes, com atalho de admin', () => {
    const t = setup(AccountPage, 'admin').textContent!;
    expect(t).toContain('Trocar senha');
    expect(t).toContain('Verificação em duas etapas');
    expect(t).toContain('Sessões abertas');
    expect(t).toContain('Usuários e auditoria');
  });

  it('conta de operador nao mostra o atalho de usuarios', () => {
    expect(setup(AccountPage, 'operador').textContent!).not.toContain('Usuários e auditoria');
  });

  it('usuarios: tabela, novo usuario e auditoria', () => {
    const t = setup(UsersPage, 'admin').textContent!;
    expect(t).toContain('Novo usuário');
    expect(t).toContain('Auditoria');
    expect(t).toContain('administrador');
  });

  it('leitor: botoes de operacao ficam desabilitados; operador: habilitados', () => {
    const ligar = (el: HTMLElement) => [...el.querySelectorAll('button')].find(b => b.textContent!.includes('Reiniciar'))!;
    expect(ligar(setup(OperatePage, 'leitor')).disabled).toBe(true);
    TestBed.resetTestingModule();
    expect(ligar(setup(OperatePage, 'operador')).disabled).toBe(false);
  });
});
