import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { Status } from '../core/models';
import { StatusStore } from '../core/status.store';
import { HealthPage } from './health.page';
import { ManagePage } from './manage.page';
import { OperatePage } from './operate.page';
import { OverviewPage } from './overview.page';
import { PortfolioPage } from './portfolio.page';
import { TradesPage } from './trades.page';

const STATUS: Status = {
  now: 1795530000, bars: [[1795529000000, 1700], [1795529060000, 1702], [1795529120000, 1698]],
  service: 'active', kill_file: false,
  config: { QUANT_MODE: 'testnet', QUANT_VENUE: 'kalshi', QUANT_TIMEFRAME: '1m', QUANT_SYMBOL: 'ETH/USDT:USDT' },
  health: { uptime_s: 120, restarts: 0, memory_mb: 45 },
  selfcheck: { at: '2026-11-24T12:00:00+00:00', ok: true, checks: [{ name: 'nginx ativo', ok: true, detail: 'active' }],
               tests: { ok: true, passed: 217, failed: 0, skipped: 2, seconds: 30, failures: [] },
               paper: { days: 3, equity: 1, ret_total: 0, sharpe: null, max_dd: 0, verdict: 'amostra curta' } },
  deploy: { last: { state: 'ok', msg: 'aplicado', at: 'x', id: '1' }, pacote: null },
  alerts: { canais: ['telegram'], ultima_checagem: 1795529900, estado: null },
  trades: { count: 2, pnl_total: 0.05, wins: 1, win_rate: 0.5, max_dd: -0.01,
            trades: [{ ts: '2026-11-24 10:00:00', origem: 'k', side: 1, qty: 0.002, entrada: 1700, saida: 1705, pnl: 0.01, motivo: 'stop' }],
            curve: [['a', 0.01], ['b', 0.05]] },
  venues: { kalshi: { modos: ['paper', 'testnet'], credencial: 'chave presente' } },
  portfolio: { days: 3, last_date: '2026-11-24', equity: 0.998, pnl: -0.001, series: [['a', 1], ['b', 0.998]], weights: { BTCUSDT: 0.2, ETHUSDT: -0.1 } },
  state: { last_bar: '2026-11-24 12:00:00', stop: 1690, stop_dist: 9, entry: { side: 1, qty: 0.002, price: 1699 },
           risk: { pnl: 0.01, trades: 1, halted: false }, executor: { pos: { side: 1, qty: 0.002, entry: 1699 } } },
  last_bar_age_s: 20, log: ['x INFO quant.live runner iniciado', 'x WARNING quant.live alerta'],
};

function render(page: Type<unknown>, status: Status | null = STATUS): HTMLElement {
  TestBed.configureTestingModule({
    providers: [provideHttpClient(), provideHttpClientTesting(),
                { provide: StatusStore, useValue: { data: signal(status), refresh: () => {} } }],
  });
  const f = TestBed.createComponent(page);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('paginas renderizam sem erro (pega inject() fora de contexto, templates quebrados)', () => {
  it('visao geral', () => {
    const t = render(OverviewPage).textContent!;
    expect(t).toContain('testnet · kalshi');
    expect(t).toContain('entrada 1.699,00');
  });
  it('trades', () => {
    const t = render(TradesPage).textContent!;
    expect(t).toContain('0,0500');
    expect(t).toContain('Baixar CSV');
  });
  it('carteira', () => {
    const t = render(PortfolioPage).textContent!;
    expect(t).toContain('0,9980');
    expect(t).toContain('BTC');
  });
  it('saude', () => {
    const t = render(HealthPage).textContent!;
    expect(t).toContain('217 ok');
    expect(t).toContain('nginx ativo');
  });
  it('gestao', () => {
    const t = render(ManagePage).textContent!;
    expect(t).toContain('telegram');
    expect(t).toContain('aplicado');
  });
  it('operar', () => {
    const t = render(OperatePage).textContent!;
    expect(t).toContain('Kill-switch');
    expect(t).toContain('kalshi');
  });
  it('sem dados ainda: nao quebra', () => {
    for (const p of [OverviewPage, TradesPage, PortfolioPage, HealthPage, ManagePage]) {
      TestBed.resetTestingModule();
      expect(() => render(p, null)).not.toThrow();
    }
  });
});
