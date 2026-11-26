import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Live } from '../core/models';
import { LivePage, heat } from './live.page';
import { ResearchPage } from './research.page';

const LIVE: Live = {
  em: 1795000000, er_min: 0.4, ativos: ['BTC', 'GOLD'],
  fontes: [{ nome: 'fotos do livro', idade_s: 30, limite_s: 180, detalhe: '' }, { nome: 'métricas da conta', idade_s: null, limite_s: 360, detalhe: '' }],
  ia: { t: 1795000000, ha_s: 20, modelo: 'claude-haiku-5-5', sombra: true, erro: null, analise: 'livro comprador no ouro', posicoes: [],
        funil: { universo: 145, fotos: 40, candidatos: 2, pedidos: 1, aceitos: 1 }, historico: [{ t: 1795000000, pedidos: 1, aceitos: 1 }],
        candidatos: [{ ativo: 'BTC', ret_5m_bps: 12, decisao: null, status: null, porque: '' },
                     { ativo: 'GOLD', imb_100: 0.6, decisao: 'abrir', status: 'sombra', porque: 'fluxo comprador' }] },
  robo: [{ ativo: 'BTC', barra: '2026-11-26 10:00:00', preco: 99, falta_alta_pct: 1.01, falta_baixa_pct: 5, er: 0.7, er_ok: true,
           tendencia: 1, sinal: 0, resultado: 'ok', posicao: null, travado: false, motivo: '', fluxo: 0.2 }],
};

describe('ao vivo e pesquisa', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function providers() { TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }); }

  it('mostra funil, decisão por candidato, radar e fontes, e abre a leitura do ativo clicado', () => {
    providers();
    const f = TestBed.createComponent(LivePage);
    const http = TestBed.inject(HttpTestingController);
    vi.advanceTimersByTime(1);
    http.expectOne('api/live').flush(LIVE);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const t = el.textContent!;
    for (const s of ['145', 'livro comprador no ouro', 'abrir · sombra', 'ignorado', 'sem sinal', '1,01%', 'métricas da conta: sem dado']) {
      expect(t).toContain(s);
    }
    (el.querySelector('tr.pick') as HTMLElement).click();  // o candidato com decisao vem primeiro: GOLD
    http.expectOne('api/live').flush(LIVE);
    const req = http.expectOne(r => r.url === 'api/flow');
    expect([req.request.params.get('asset'), req.request.params.get('horas')]).toEqual(['GOLD', '6']);
    req.flush({ ativo: 'GOLD', serie: [[1795000000, 3.5, 0.1, 5], [1795000060, 3.6, 0.4, 5]], decisoes: [] });
    f.detectChanges();
    expect(el.textContent).toContain('Desequilíbrio do livro');
    expect(el.querySelectorAll('app-line-chart svg').length).toBe(2);
  });

  it('pinta a celula pela direcao e intensidade', () => {
    expect(heat(null, 10)).toBe('transparent');
    expect(heat(100, 10)).toContain('--ok) 32%');
    expect(heat(-5, 10)).toContain('--bad) 16%');
  });

  it('pesquisa lista os estudos e filtra pela busca', () => {
    providers();
    const f = TestBed.createComponent(ResearchPage);
    TestBed.inject(HttpTestingController).expectOne('api/research').flush({ estudos: [
      { nome: 'vela_30min', hipotese: 'prever a vela', resultado: 'perde', status: 'reprovada', tom: 'bad' },
      { nome: 'eth_flow', hipotese: 'agressão', resultado: '1 dia', status: 'hipótese', tom: 'warn' }] });
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.textContent).toContain('vela_30min');
    const input = el.querySelector('input')!;
    input.value = 'agress';
    input.dispatchEvent(new Event('input'));
    f.detectChanges();
    expect(el.textContent).not.toContain('vela_30min');
    expect(el.textContent).toContain('eth_flow');
  });
});
