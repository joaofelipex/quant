import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ActionResult, OrderRequest, OrderResult, SettingsResponse, Status, TradesSummary } from './models';

/** Cabecalho exigido pelo backend em todo POST (barra CSRF: so JS da mesma origem consegue enviá-lo). */
export const CONTROL_HEADERS = { 'X-Quant-Control': '1' };

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  // caminhos relativos: o painel vive em /controle/ atras do nginx (e na raiz no `ng serve`)
  status(): Observable<Status> { return this.http.get<Status>('api/status'); }
  settings(): Observable<SettingsResponse> { return this.http.get<SettingsResponse>('api/settings'); }
  trades(): Observable<TradesSummary> { return this.http.get<TradesSummary>('api/trades'); }

  post(path: string, body?: unknown): Observable<ActionResult> {
    return this.http.post<ActionResult>(path, body ?? null, { headers: CONTROL_HEADERS });
  }

  runner(verb: 'start' | 'stop' | 'restart') { return this.post(`api/runner/${verb}`); }
  saveSettings(values: Record<string, string>) { return this.post('api/settings', values); }
  /** Pede uma ordem manual (so demo); devolve o id. O resultado sai de `orderResult()` quando a unit terminar. */
  order(req: OrderRequest): Observable<ActionResult & { id?: string }> { return this.post('api/order', req); }
  orderResult(): Observable<OrderResult> { return this.http.get<OrderResult>('api/order'); }
  kill() { return this.post('api/kill'); }
  runSelfcheck() { return this.post('api/selfcheck/run'); }
  runDeploy() { return this.post('api/deploy/run'); }
  rollback() { return this.post('api/deploy/rollback'); }
  testAlert() { return this.post('api/alerts/test'); }
}

/** Mensagem legivel de um erro HTTP do backend (`{erro: ...}`) ou de rede. */
export function errMsg(e: unknown): string {
  if (e instanceof HttpErrorResponse) {
    const body = e.error as { erro?: string } | null;
    return body?.erro ?? (e.status ? `HTTP ${e.status}` : 'sem conexão');
  }
  return e instanceof Error ? e.message : String(e);
}
