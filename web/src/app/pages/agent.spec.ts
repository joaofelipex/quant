import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { AuthService, Me } from '../core/auth.service';
import { AgentStatus } from '../core/models';
import { AgentPage } from './agent.page';

const me = (role: Me['role']): Me => ({ id: 'a', user: 'u', role, sid: 's', totp: false });

const STATUS = (over: Partial<AgentStatus> = {}): AgentStatus => ({
  config: { enabled: false, model: 'claude-sonnet-5-5', interval_min: 10, max_usd: 15, max_positions: 5, max_daily_loss: 2,
            long_only: true, stop_min: 0.5, stop_max: 5, cooldown_min: 20, max_actions: 3, max_hold_h: 24, candidates: 12, universe: 'tudo', edge_min: 2, shadow: false, aggressive: false },
  chave: true, modelos: ['claude-sonnet-5-5', 'claude-haiku-5-5'], pnl_hoje: -0.5, state: { ciclos: 4, tokens: 5000, last_error: null },
  livro: { NVDA: { opened_at: 1795000000, reason: 'fluxo comprador', side: 1, usd: 12 } },
  decisoes: [{ t: 1795000100, analise: 'Sem vantagem clara.', universo: 145, fotos: 140, pnl_dia: -0.5, uso: { input_tokens: 3000, output_tokens: 200 },
               acoes: [{ status: 'recusada', acao: 'abrir', ativo: 'AAPL', usd: 10, stop_pct: 9, motivo: 'tendencia', why: 'stop deve ficar entre 0.5% e 5%' }] }],
  ...over,
});

function render(role: Me['role'], status: AgentStatus): HTMLElement {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
  TestBed.inject(AuthService).me.set(me(role));
  const f = TestBed.createComponent(AgentPage);
  f.detectChanges();
  TestBed.inject(HttpTestingController).expectOne('api/agent').flush(status);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const btn = (el: HTMLElement, txt: string) => [...el.querySelectorAll('button')].find(b => b.textContent!.includes(txt))!;

describe('pagina da IA', () => {
  it('mostra posicoes, decisoes e a recusa com o motivo da trava', () => {
    const t = render('admin', STATUS()).textContent!;
    expect(t).toContain('NVDA');
    expect(t).toContain('fluxo comprador');
    expect(t).toContain('Sem vantagem clara.');
    expect(t).toContain('recusada');
    expect(t).toContain('stop deve ficar entre');
    expect(t).toContain('travas no código');
  });

  it('sem chave da IA avisa como gravar e nao deixa ligar', () => {
    const el = render('admin', STATUS({ chave: false }));
    expect(el.textContent).toContain('definir-chave-ia.sh');
    expect(btn(el, 'Ligar a IA').disabled).toBe(true);
  });

  it('com chave o operador pode ligar; leitor nao', () => {
    expect(btn(render('operador', STATUS()), 'Ligar a IA').disabled).toBe(false);
    TestBed.resetTestingModule();
    expect(btn(render('leitor', STATUS()), 'Ligar a IA').disabled).toBe(true);
  });

  it('ligada mostra Desligar e o estado', () => {
    const st = STATUS();
    st.config.enabled = true;
    const el = render('operador', st);
    expect(btn(el, 'Desligar')).toBeTruthy();
    expect(el.textContent).toContain('ligada');
  });

  it('so administrador edita os limites', () => {
    expect(render('admin', STATUS()).textContent).not.toContain('Só administrador altera');
    TestBed.resetTestingModule();
    const oper = render('operador', STATUS());
    expect(oper.textContent).toContain('Só administrador altera');
    expect(btn(oper, 'Salvar limites').disabled).toBe(true);
  });

  it('erro do ultimo ciclo aparece em destaque', () => {
    const st = STATUS();
    st.state.last_error = 'HTTP 401: invalid x-api-key';
    expect(render('admin', st).textContent).toContain('invalid x-api-key');
  });
});
