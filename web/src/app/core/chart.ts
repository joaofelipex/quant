export interface ChartLine { value: number; color: string; label: string }

export interface ChartModel {
  points: string;
  area: string;
  xs: number[];
  ys: number[];
  values: number[];
  lines: { y: number; color: string; label: string; value: number }[];
  baseline: number | null;
  lo: number;
  hi: number;
  x: (i: number) => number;
}

export const CHART_W = 800;
const PAD_X = 10;

/** Converte uma serie em coordenadas SVG; linhas de referencia (entrada, stop) entram na escala. */
export function buildChart(values: number[], height: number, opts: { lines?: ChartLine[]; baseline?: number } = {},
                           padFrac = 0.08, width = CHART_W): ChartModel | null {
  const v = values.filter(x => x != null && Number.isFinite(x));
  if (v.length < 2) return null;
  const extra = (opts.lines ?? []).map(l => l.value);
  const all = [...v, ...extra, ...(opts.baseline != null ? [opts.baseline] : [])];
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * padFrac || 0.001;
  const top = 10, h = height - 20;
  const y = (val: number) => top + h - ((val - (lo - pad)) * h) / (hi - lo + 2 * pad);
  const x = (i: number) => PAD_X + (i * (width - 2 * PAD_X)) / (v.length - 1);
  const xs = v.map((_, i) => x(i)), ys = v.map(val => y(val));
  const pts = xs.map((px, i) => `${px.toFixed(1)},${ys[i].toFixed(1)}`);
  return {
    points: pts.join(' '),
    area: `M${pts[0]} L${pts.slice(1).join(' L')} L${xs[xs.length - 1].toFixed(1)},${height} L${xs[0].toFixed(1)},${height} Z`,
    xs, ys, values: v,
    lines: (opts.lines ?? []).map(l => ({ ...l, y: y(l.value) })),
    baseline: opts.baseline != null ? y(opts.baseline) : null,
    lo, hi, x,
  };
}
