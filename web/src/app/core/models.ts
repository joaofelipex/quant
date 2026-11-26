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

export interface ActionResult {
  ok?: boolean; erro?: string; canais?: string[]; restart_needed?: boolean; reset?: number; religado?: boolean;
}

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

export interface AgentConfig {
  enabled: boolean; model: string; interval_min: number; max_usd: number; max_positions: number; max_daily_loss: number;
  long_only: boolean; stop_min: number; stop_max: number; cooldown_min: number; max_actions: number; max_hold_h: number;
  candidates: number; universe: string; edge_min: number; shadow: boolean; aggressive: boolean;
}
export interface AgentAction {
  acao?: string; ativo?: string; status: string; usd?: number; stop_pct?: number; motivo?: string; why?: string;
  detalhe?: string; aviso?: string; ajustado?: boolean; fechada_por_seguranca?: boolean;
}
export interface AgentDecision {
  t: number; analise?: string; erro?: string | null; universo?: number; fotos?: number; pnl_dia?: number;
  uso?: { input_tokens?: number; output_tokens?: number }; acoes: AgentAction[];
}
export interface AgentStatus {
  config: AgentConfig; chave: boolean; modelos: string[]; pnl_hoje: number; decisoes: AgentDecision[];
  state: { last_run?: number; last_error?: string | null; ciclos?: number; tokens?: number };
  livro: Record<string, { opened_at: number; reason: string; side: number; usd: number }>;
}

/** Linha de resultado agrupado (por origem, classe ou dia), em USD, conforme a corretora. */
export interface MetricGroup { nome: string; posicoes: number; fechadas: number; ganhos: number; bruto: number; taxa: number; liquido: number }
/** GET api/metrics: retrato gravado pela unit quant-metrics. `disponivel: false` = ainda nao ha coleta. */
export interface Metrics {
  disponivel: boolean; idade_s: number; em: number;
  conta: { patrimonio: number; disponivel: number | null; inicial_implicito: number; liquido: number; bruto: number; taxas: number; funding: number; aberto: number; execucoes: number };
  por_origem: MetricGroup[]; por_classe: MetricGroup[]; por_dia: MetricGroup[];
  extremos: { asset: string; quem: string; liquido: number; em: number; corretora: boolean }[];
  posicoes: { asset: string; quem: string; qtd: number; entrada: number; aberto: number; stop: boolean | null }[];
  registro: { local: number; corretora: number; diferenca: number };
  ia: { ligada: boolean; sombra: boolean; intervalo_min: number; modelo: string; ciclos_24h: number; erros_24h: number; falhas_24h: number;
        ultimo_ciclo_s: number | null; ultima_analise: string; recusas: { motivo: string; n: number }[] };
  sombra: { ciclos: number; abertas: number; fechadas: number; ganhos: number; media_bps: number | null; total_bps: number;
            ultimas: { t: number; asset: string; bps: number }[] };
  servicos: { unit: string; nome: string; estado: string }[];
  travados: { asset: string; motivo: string }[];
  kill: boolean;
  equity: [number, number][];
  problemas: { nivel: 'bad' | 'warn'; texto: string }[];
}

/** GET api/live: o que a IA e o robo estao lendo agora. */
export interface LiveCandidate {
  ativo: string; ret_5m_bps?: number | null; ret_15m_bps?: number | null; ret_60m_bps?: number | null; imb_100?: number; spread_bps?: number;
  custo_ida_volta_bps?: number; decisao: string | null; status: string | null; porque: string;
}
export interface RadarRow {
  ativo: string; barra: string | null; preco: number | null; falta_alta_pct: number | null; falta_baixa_pct: number | null; er: number | null; er_ok: boolean;
  tendencia: number | null; sinal: number | null; resultado: string | null; posicao: number | null; travado: boolean; motivo: string; fluxo: number | null;
}
export interface Live {
  em: number; er_min: number; ativos: string[]; robo: RadarRow[];
  fontes: { nome: string; idade_s: number | null; limite_s: number; detalhe: string }[];
  ia: null | {
    t: number; ha_s: number; modelo: string; sombra: boolean; erro: string | null; analise: string; posicoes: string[];
    funil: { universo: number; fotos: number; candidatos: number; pedidos: number; aceitos: number };
    candidatos: LiveCandidate[]; historico: { t: number; pedidos: number; aceitos: number }[];
  };
}
/** GET api/flow: [epoch, meio do livro, desequilibrio 1%, spread bps]. */
export interface FlowSeries { ativo: string; serie: [number, number, number, number][]; decisoes: { t: number; acao?: string; status: string; porque: string }[] }
export interface Study { nome: string; hipotese: string; resultado: string; status: string; tom: Tone }

export type Tone = '' | 'ok' | 'bad' | 'warn';
