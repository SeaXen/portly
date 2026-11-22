import { describe, it, expect } from 'vitest';
import { resolveViewChord } from './shortcuts';

describe('resolveViewChord', () => {
  it('treats a second g within the window as the grid chord', () => {
    const first = resolveViewChord('G', 0, 1000);
    expect(first).toEqual({ view: null, gPressedAt: 1000 });
    expect(resolveViewChord('g', first.gPressedAt, 1500)).toEqual({ view: 'grid', gPressedAt: 0 });
  });

  it('resolves gt/gb/gl and ignores chords after the window expires', () => {
    expect(resolveViewChord('t', 1000, 1100).view).toBe('table');
    expect(resolveViewChord('b', 1000, 1100).view).toBe('board');
    expect(resolveViewChord('l', 1000, 1100).view).toBe('list');
    expect(resolveViewChord('t', 1000, 2100)).toEqual({ view: null, gPressedAt: 1000 });
  });

  it('starts a fresh window on a standalone g when no chord is pending', () => {
    expect(resolveViewChord('g', 0, 1000)).toEqual({ view: null, gPressedAt: 1000 });
    expect(resolveViewChord('G', 0, 1000)).toEqual({ view: null, gPressedAt: 1000 });
  });
});
