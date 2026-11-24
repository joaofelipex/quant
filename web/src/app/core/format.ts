import { Tone } from './models';

export const fmt = (x: number | null | undefined, d = 2): string =>
  x == null || Number.isNaN(x) ? '—'
    : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });

export const pct = (x: number | null | undefined, d = 2): string =>
  x == null || Number.isNaN(x) ? '—' : (x >= 0 ? '+' : '') + (x * 100).toFixed(d).replace('.', ',') + '%';

export function dur(s: number | null | undefined): string {
  if (s == null) return '—';
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 172800) return `${fmt(s / 3600, 1)} h`;
  return `${fmt(s / 86400, 1)} d`;
}

export const tone = (x: number | null | undefined, neutral = 0): Tone =>
  x == null ? '' : x > neutral ? 'ok' : x < neutral ? 'bad' : '';

export const hhmm = (ms: number): string =>
  new Date(ms).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

export const TIMEFRAME_S: Record<string, number> = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600 };

const isErr = (l: string) => /\b(ERROR|WARNING|CRITICAL|Traceback)\b/.test(l);
const isKey = (l: string) => isErr(l) || /entrada|saida|saída|fechad|stop|kill|bloquead|perda|ordem|fill/i.test(l);

export type LogFilter = 'all' | 'key' | 'err';

export function filterLog(lines: string[], f: LogFilter): string[] {
  return lines.filter(l => f === 'all' || (f === 'err' ? isErr(l) : isKey(l)));
}

export const logTone = (l: string): Tone =>
  /\b(ERROR|CRITICAL|Traceback)\b/.test(l) ? 'bad' : /WARNING/.test(l) ? 'warn' : '';
