export type ViewType = 'table' | 'grid' | 'list' | 'board';

const CHORD_VIEWS: Record<string, ViewType> = {
  g: 'grid',
  t: 'table',
  b: 'board',
  l: 'list',
};

/**
 * Resolve a g-chord. The chord is checked before the standalone-g reset so
 * `g` then `g` can actually select the grid view.
 */
export function resolveViewChord(
  key: string,
  gPressedAt: number,
  now: number,
): { view: ViewType | null; gPressedAt: number } {
  const k = key.toLowerCase();
  if (now - gPressedAt < 1000) {
    const view = CHORD_VIEWS[k];
    if (view) return { view, gPressedAt: 0 };
  }
  if (k === 'g') return { view: null, gPressedAt: now };
  return { view: null, gPressedAt };
}
