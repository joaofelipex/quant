import { describe, expect, it } from 'vitest';
import { Status } from './models';
import { computeBanner } from './status.store';

const base = (over: Partial<Status> = {}): Status => ({
  now: 0, bars: [], service: 'active', kill_file: false, config: { QUANT_TIMEFRAME: '1m' },
  health: { uptime_s: 10, restarts: 0, memory_mb: 40 }, selfcheck: null,
  deploy: { last: null, pacote: null }, alerts: { canais: [], ultima_checagem: null, estado: null },
  trades: { count: 0, pnl_total: 0, wins: 0, win_rate: null, max_dd: 0, trades: [], curve: [] },
  venues: {}, portfolio: null, state: { last_bar: null, stop: null, stop_dist: null, entry: null, risk: {}, executor: null },
  last_bar_age_s: 30, log: [], ...over,
});

describe('computeBanner', () => {
  it('carregando e sem conexao', () => {
    expect(computeBanner(null, null).tone).toBe('');
    expect(computeBanner(null, 'HTTP 502').tone).toBe('bad');
    expect(computeBanner(base(), 'sem conexão').text).toContain('desatualizados');
  });

  it('prioridade: kill > parado > trava de risco > barra velha > normal', () => {
    expect(computeBanner(base({ kill_file: true, service: 'inactive' }), null).text).toContain('KILL');
    expect(computeBanner(base({ service: 'inactive' }), null).text).toContain('não está ativo');
    const halted = base({ state: { ...base().state!, risk: { halted: true } } });
    expect(computeBanner(halted, null).tone).toBe('warn');
    expect(computeBanner(base({ last_bar_age_s: 500 }), null).text).toContain('sem barra nova');
    expect(computeBanner(base(), null)).toEqual({ text: 'runner ativo e dentro do normal', tone: 'ok' });
  });

  it('o limite de barra velha depende do timeframe', () => {
    const tf5 = base({ config: { QUANT_TIMEFRAME: '5m' }, last_bar_age_s: 500 });
    expect(computeBanner(tf5, null).tone).toBe('ok');  // 3 x 300 s = 900 s
  });
});
