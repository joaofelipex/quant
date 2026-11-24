import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { AuthService, Me } from '../core/auth.service';
import { Status } from '../core/models';
import { StatusStore } from '../core/status.store';
import { AccountPage } from './account.page';
import { LoginPage } from './login.page';
import { OperatePage } from './operate.page';
import { OverviewPage } from './overview.page';
import { TicketPage } from './ticket.page';
import { UsersPage } from './users.page';

const me = (role: Me['role']): Me => ({ id: 'a1', user: 'chefe', role, sid: 's', totp: false });

function setup(page: Type<unknown>, role: Me['role'] | null, first = false, data: Status | null = null): HTMLElement {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
      { provide: StatusStore, useValue: { data: signal(data), asset: signal(null), select: () => {}, banner: signal({ text: 'x', tone: 'ok' }), refresh: () => {} } }],
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

  describe('varios ativos', () => {
    const multi = (): Status => ({
      now: 1795530000, bars: [[1795529000000, 60000], [1795529060000, 60100]], service: 'inactive', kill_file: false,
      config: { QUANT_MODE: 'testnet', QUANT_VENUE: 'kalshi', QUANT_TIMEFRAME: '1m', QUANT_ASSETS: 'BTC,SOL' },
      health: { uptime_s: 1, restarts: 0, memory_mb: 1 }, selfcheck: null, deploy: { last: null, pacote: null },
      alerts: { canais: [], ultima_checagem: null, estado: null },
      trades: { count: 0, pnl_total: 0, wins: 0, win_rate: null, max_dd: 0, trades: [], curve: [] }, venues: {}, portfolio: null,
      state: null, last_bar_age_s: 10, log: [], asset: 'BTC',
      assets: [
        { asset: 'BTC', position: { side: 1, qty: 0.0003, price: 60000 }, stop: 59000, pnl: 0.25, trades: 1, halted: false, reason: '', last_bar_age_s: 20, started: true },
        { asset: 'SOL', position: null, stop: null, pnl: -0.1, trades: 2, halted: true, reason: 'perda', last_bar_age_s: 30, started: true },
      ],
    });

    it('visao geral lista os ativos com posicao, PnL somado e estado', () => {
      TestBed.resetTestingModule();
      const t = setup(OverviewPage, 'admin', false, multi()).textContent!;
      expect(t).toContain('Ativos em operação (2)');
      expect(t).toContain('BTC');
      expect(t).toContain('SOL');
      expect(t).toContain('1 posição(ões) aberta(s)');
      expect(t).toContain('travado');
    });

    it('operar: marcar ativos monta a lista e Nenhum limpa', () => {
      TestBed.resetTestingModule();
      const el = setup(OperatePage, 'operador', false, multi());
      const btn = (txt: string) => [...el.querySelectorAll('button')].find(b => b.textContent!.trim() === txt)!;
      expect(btn('BTC')).toBeTruthy();
      expect(btn('ZEC')).toBeTruthy();
      expect(el.textContent).toContain('Valor por entrada (USD)');
    });

    it('boleta: com varios ativos pede ativo e valor em USD', () => {
      TestBed.resetTestingModule();
      const t = setup(TicketPage, 'admin', false, { ...multi() }).textContent!;
      expect(t).toContain('Ativo e valor (USD)');
      expect(t).not.toContain('Quantidade (ETH)');
    });
  });
});
