import { describe, expect, it } from 'vitest';
import { buildChart } from './chart';

describe('buildChart', () => {
  it('precisa de ao menos 2 pontos validos', () => {
    expect(buildChart([1], 100)).toBeNull();
    expect(buildChart([NaN, 1], 100)).toBeNull();
  });

  it('mapeia a serie para dentro do viewBox, com o maior valor no topo', () => {
    const m = buildChart([1, 2, 3], 100)!;
    const ys = m.points.split(' ').map(p => Number(p.split(',')[1]));
    expect(ys[2]).toBeLessThan(ys[1]);
    expect(ys[1]).toBeLessThan(ys[0]);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...ys)).toBeLessThanOrEqual(100);
  });

  it('linhas de referencia entram na escala (stop abaixo da serie nao sai do grafico)', () => {
    const m = buildChart([100, 101, 102], 100, { lines: [{ value: 90, color: 'red', label: 'stop' }], baseline: 100 })!;
    expect(m.lines[0].y).toBeGreaterThan(m.baseline!);
    expect(m.lines[0].y).toBeLessThanOrEqual(100);
    expect(m.lo).toBe(90);
  });

  it('serie constante nao divide por zero', () => {
    const m = buildChart([5, 5, 5], 100)!;
    expect(m.points).not.toContain('NaN');
  });
});
