import { describe, expect, it } from 'vitest';
import { dur, filterLog, fmt, logTone, pct, tone } from './format';

describe('format', () => {
  it('formata numeros em pt-BR e trata nulos', () => {
    expect(fmt(1234.5)).toBe('1.234,50');
    expect(fmt(null)).toBe('—');
    expect(fmt(NaN)).toBe('—');
    expect(pct(0.0123)).toBe('+1,23%');
    expect(pct(-0.5, 0)).toBe('-50%');
    expect(pct(undefined)).toBe('—');
  });

  it('duracoes em escala legivel', () => {
    expect(dur(45)).toBe('45 s');
    expect(dur(600)).toBe('10 min');
    expect(dur(7200)).toBe('2,0 h');
    expect(dur(86400 * 3)).toBe('3,0 d');
    expect(dur(null)).toBe('—');
  });

  it('tom pelo sinal', () => {
    expect(tone(1)).toBe('ok');
    expect(tone(-1)).toBe('bad');
    expect(tone(0)).toBe('');
    expect(tone(1.2, 1)).toBe('ok');
    expect(tone(null)).toBe('');
  });

  it('filtra o log por severidade', () => {
    const log = ['x INFO quant.live runner iniciado', 'x WARNING quant.live entrada bloqueada', 'x INFO quant.live entrada +1 @ 1', 'x ERROR boom'];
    expect(filterLog(log, 'all')).toHaveLength(4);
    expect(filterLog(log, 'err')).toEqual([log[1], log[3]]);
    expect(filterLog(log, 'key')).toEqual([log[1], log[2], log[3]]);
    expect(logTone(log[3])).toBe('bad');
    expect(logTone(log[1])).toBe('warn');
    expect(logTone(log[0])).toBe('');
  });
});
