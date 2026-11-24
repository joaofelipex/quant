import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { ApiService, errMsg } from './api.service';

describe('ApiService', () => {
  const setup = () => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    return { api: TestBed.inject(ApiService), http: TestBed.inject(HttpTestingController) };
  };

  it('todo POST leva o cabecalho anti-CSRF; GET nao precisa', () => {
    const { api, http } = setup();
    api.kill().subscribe();
    const kill = http.expectOne('api/kill');
    expect(kill.request.method).toBe('POST');
    expect(kill.request.headers.get('X-Quant-Control')).toBe('1');
    kill.flush({ kill_file: true });

    api.saveSettings({ QUANT_QTY: '0.01' }).subscribe();
    const save = http.expectOne('api/settings');
    expect(save.request.headers.get('X-Quant-Control')).toBe('1');
    expect(save.request.body).toEqual({ QUANT_QTY: '0.01' });
    save.flush({});

    api.status().subscribe();
    const get = http.expectOne('api/status');
    expect(get.request.method).toBe('GET');
    get.flush({});
    http.verify();
  });

  it('usa caminhos relativos (o painel vive em /controle/)', () => {
    const { api, http } = setup();
    api.runner('restart').subscribe();
    expect(http.expectOne(r => !r.url.startsWith('/')).request.url).toBe('api/runner/restart');
  });

  it('mensagem de erro vem do corpo {erro} do backend', () => {
    const { api, http } = setup();
    let msg = '';
    api.runner('start').subscribe({ error: e => (msg = errMsg(e)) });
    http.expectOne('api/runner/start').flush({ erro: 'arquivo KILL presente' }, { status: 409, statusText: 'Conflict' });
    expect(msg).toBe('arquivo KILL presente');
  });
});
