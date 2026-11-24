/** Contratos da API do painel (quant/control.py). Campos opcionais refletem o que a VM pode não ter ainda. */

export interface Position { side: number; qty: number; entry: number }

export interface RunnerState {
  last_bar: string | null;
  stop: number | null;
  stop_dist: number | null;
  entry: { side: number; qty: number; price: number } | null;
  risk: { day?: string; pnl?: number; trades?: number; halted?: boolean; reason?: string };
  executor: { pos?: unknown; basis?: number } | null;
}

export interface Health { uptime_s: number | null; restarts: number | null; memory_mb: number | null }

export interface PortfolioSummary {
  days: number; last_date: string; equity: number | null; pnl: number | null;
  series: [string, number | null][]; weights: Record<string, number | null>;
}

export interface SelfcheckReport {
  at: string; ok: boolean;
  tests: { ok: boolean; passed: number; failed: number; skipped: number; seconds: number; failures: string[] } | null;
  checks: { name: string; ok: boolean; detail: string }[];
  paper: { days: number; equity: number | null; ret_total: number | null; sharpe: number | null; max_dd: number;
           verdict: string } | null;
}

export interface Trade {
  ts: string; origem: string; side: number; qty: number; entrada: number; saida: number; pnl: number; motivo: string;
}

export interface TradesSummary {
  count: number; pnl_total: number; wins: number; win_rate: number | null; max_dd: number;
  trades: Trade[]; curve: [string, number][];
}

export interface VenueInfo { modos: string[]; credencial: string }

export interface DeployStatus {
  last: { state: 'rodando' | 'ok' | 'erro'; msg: string; at: string; id: string } | null;
  pacote: { bytes: number; mtime: number } | null;
}

export interface AlertsStatus { canais: string[]; ultima_checagem: number | null; estado: unknown }

export interface AssetRow {
  asset: string; position: { side: number; qty: number; price: number } | null; stop: number | null; pnl: number;
  trades: number; halted: boolean; reason: string; last_bar_age_s: number | null; started: boolean;
}

export interface Status {
  now: number;
  asset?: string | null;
  assets?: AssetRow[];
  bars: [number, number][];
  service: string;
  kill_file: boolean;
  config: Record<string, string>;
  health: Health;
  selfcheck: SelfcheckReport | null;
  deploy: DeployStatus;
  alerts: AlertsStatus;
  trades: TradesSummary;
  venues: Record<string, VenueInfo>;
  portfolio: PortfolioSummary | null;
  state: RunnerState | null;
  last_bar_age_s: number | null;
  log: string[];
}

export interface SettingsResponse {
  saved: Record<string, string>;
  effective: Record<string, string>;
  options: Record<string, string[]>;
}

export interface ActionResult { ok?: boolean; erro?: string; canais?: string[]; restart_needed?: boolean }

/** Posicao na corretora, vista pela boleta manual (quant/manual.py). */
export interface OrderPosition {
  side: number; qty: number; entry: number; stop: boolean | null; price: number | null; upnl: number | null;
}
/** Resposta de GET api/order: `pendente` ate a unit quant-order gravar o resultado do pedido `id`. */
export interface OrderResult {
  id?: string; ok?: boolean; msg?: string; aviso?: string; pendente?: boolean; position?: OrderPosition | null;
}
export interface OrderRequest {
  action: 'status' | 'open' | 'close' | 'stop'; side?: 1 | -1; qty?: number; usd?: number; asset?: string | null; stop_pct?: number | null;
}

export type Tone = '' | 'ok' | 'bad' | 'warn';
