import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Metrics } from '../core/models';
import { ObservePage, money } from './observe.page';

const DATA: Metrics = {
  disponivel: true, idade_s: 40, em: 1795000000,
  conta: { patrimonio: 448.3, disponivel: 0, inicial_implicito: 500, liquido: -51.7, bruto: -47.6, taxas: 4.1, funding: -0.01, aberto: 0.02, execucoes: 708 },
  por_origem: [{ nome: 'ia', posicoes: 3, fechadas: 2, ganhos: 1, bruto: 1, taxa: 0.5, liquido: 0.5 }],
  por_classe: [], por_dia: [], extremos: [],
  posicoes: [{ asset: 'GOLD', quem: 'ia', qtd: 1, entrada: 3.5, aberto: 0.1, stop: false }],
  registro: { local: 1, corretora: -1, diferenca: 2 },
  ia: { ligada: true, sombra: true, intervalo_min: 5, modelo: 'claude-haiku-5-5', ciclos_24h: 100, erros_24h: 0, falhas_24h: 0, ultimo_ciclo_s: 30,
        ultima_analise: 'sem vantagem', recusas: [{ motivo: 'alvo nao cobre o custo', n: 4 }] },
  sombra: { ciclos: 10, abertas: 2, fechadas: 1, ganhos: 0, media_bps: -25, total_bps: -25, ultimas: [{ t: 1795000000, asset: 'SILVER', bps: -25 }] },
  servicos: [{ unit: 'quant-live.service', nome: 'robô de regras', estado: 'failed' }],
  travados: [], kill: false, equity: [[1795000000, 448], [1795000120, 448.3]],
  problemas: [{ nivel: 'bad', texto: 'GOLD: posição aberta SEM stop na corretora' }],
};

describe('observatório', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function open(body: unknown): HTMLElement {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    const f = TestBed.createComponent(ObservePage);
    vi.advanceTimersByTime(1);
    TestBed.inject(HttpTestingController).expectOne('api/metrics').flush(body as object);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('mostra o que precisa de atenção, o líquido, a posição sem stop e a sombra', () => {
    const t = open(DATA).textContent!;
    expect(t).toContain('posição aberta SEM stop');
    expect(t).toContain('−US$ 51,70');
    expect(t).toContain('em sombra');
    expect(t).toContain('Amostra pequena');
    expect(t).toContain('-0,25%');
    expect(t).toContain('robô de regras · failed');
  });

  it('sem coleta explica o que ligar', () => {
    expect(open({ disponivel: false }).textContent!).toContain('quant-metrics.timer');
  });

  it('avisa quando os números estão velhos', () => {
    expect(open({ ...DATA, idade_s: 900 }).textContent!).toContain('Números parados');
  });

  it('formata dinheiro com sinal', () => {
    expect([money(1.5), money(-1.5), money(0), money(null)]).toEqual(['+US$ 1,50', '−US$ 1,50', 'US$ 0,00', '—']);
  });
});
