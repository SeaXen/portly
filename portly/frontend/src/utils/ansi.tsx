import React from 'react';

// Standard ANSI 16-color palette
const FG_COLORS: Record<number, string> = {
  30: '#6b7280', // black/gray
  31: '#f87171', // red
  32: '#4ade80', // green
  33: '#fbbf24', // yellow
  34: '#60a5fa', // blue
  35: '#c084fc', // magenta
  36: '#2dd4bf', // cyan
  37: '#f3f4f6', // white
  90: '#9ca3af', // bright black
  91: '#fca5a5', // bright red
  92: '#86efac', // bright green
  93: '#fde047', // bright yellow
  94: '#93c5fd', // bright blue
  95: '#e9d5ff', // bright magenta
  96: '#5eead4', // bright cyan
  97: '#ffffff', // bright white
};

const BG_COLORS: Record<number, string> = {
  40: '#1f2937',
  41: '#991b1b',
  42: '#166534',
  43: '#854d0e',
  44: '#1e40af',
  45: '#6b21a8',
  46: '#155e75',
  47: '#e5e7eb',
  100: '#374151',
  101: '#b91c1c',
  102: '#15803d',
  103: '#a16207',
  104: '#1d4ed8',
  105: '#7e22ce',
  106: '#0e7490',
  107: '#f9fafb',
};

function get256Color(n: number): string {
  if (n < 8) return FG_COLORS[30 + n] || '#f3f4f6';
  if (n < 16) return FG_COLORS[90 + (n - 8)] || '#ffffff';
  if (n >= 16 && n <= 231) {
    const idx = n - 16;
    const r = Math.floor(idx / 36) * 51;
    const g = Math.floor((idx % 36) / 6) * 51;
    const b = (idx % 6) * 51;
    return `rgb(${r},${g},${b})`;
  }
  if (n >= 232 && n <= 255) {
    const gray = (n - 232) * 10 + 8;
    return `rgb(${gray},${gray},${gray})`;
  }
  return '#f3f4f6';
}

interface SpanSegment {
  text: string;
  fg?: string;
  bg?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

/**
 * Strips non-SGR ANSI escape sequences (e.g. cursor moves, clear screen)
 */
function cleanAnsiLine(raw: string): string {
  // eslint-disable-next-line no-control-regex -- ANSI escape sequences are intentional here.
  return raw.replace(/(?:\x1b|\u001b)\[[0-9;]*[A-HJKSTfimnsu]/g, (match) => {
    return match.endsWith('m') ? match : '';
  });
}

/**
 * Parses an ANSI formatted log string into styled React spans.
 */
export function parseAnsiToReact(raw: string): React.ReactNode {
  if (!raw) return '';
  const text = cleanAnsiLine(raw);
  // eslint-disable-next-line no-control-regex -- ANSI escape sequences are intentional here.
  const regex = /(?:\x1b|\u001b)\[([0-9;]*)m/g;

  let currentFg: string | undefined;
  let currentBg: string | undefined;
  let bold = false;
  let dim = false;
  let italic = false;
  let underline = false;

  const segments: SpanSegment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const part = text.substring(lastIndex, match.index);
      if (part) {
        segments.push({
          text: part,
          fg: currentFg,
          bg: currentBg,
          bold,
          dim,
          italic,
          underline,
        });
      }
    }

    const codeStr = match[1] || '0';
    const codes = codeStr.split(';').map((c) => parseInt(c, 10) || 0);

    for (let i = 0; i < codes.length; i++) {
      const code = codes[i];
      if (code === 0) {
        currentFg = undefined;
        currentBg = undefined;
        bold = false;
        dim = false;
        italic = false;
        underline = false;
      } else if (code === 1) {
        bold = true;
      } else if (code === 2) {
        dim = true;
      } else if (code === 3) {
        italic = true;
      } else if (code === 4) {
        underline = true;
      } else if (code === 22) {
        bold = false;
        dim = false;
      } else if (code === 23) {
        italic = false;
      } else if (code === 24) {
        underline = false;
      } else if (code >= 30 && code <= 37) {
        currentFg = FG_COLORS[code];
      } else if (code === 38 && codes[i + 1] === 5 && codes[i + 2] !== undefined) {
        currentFg = get256Color(codes[i + 2]);
        i += 2;
      } else if (code === 39) {
        currentFg = undefined;
      } else if (code >= 40 && code <= 47) {
        currentBg = BG_COLORS[code];
      } else if (code === 48 && codes[i + 1] === 5 && codes[i + 2] !== undefined) {
        currentBg = get256Color(codes[i + 2]);
        i += 2;
      } else if (code === 49) {
        currentBg = undefined;
      } else if (code >= 90 && code <= 97) {
        currentFg = FG_COLORS[code];
      } else if (code >= 100 && code <= 107) {
        currentBg = BG_COLORS[code];
      }
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    segments.push({
      text: text.substring(lastIndex),
      fg: currentFg,
      bg: currentBg,
      bold,
      dim,
      italic,
      underline,
    });
  }

  if (segments.length === 0) return null;

  return (
    <>
      {segments.map((seg, idx) => {
        const style: React.CSSProperties = {};
        if (seg.fg) style.color = seg.fg;
        if (seg.bg) style.backgroundColor = seg.bg;
        if (seg.bold) style.fontWeight = 700;
        if (seg.dim) style.opacity = 0.65;
        if (seg.italic) style.fontStyle = 'italic';
        if (seg.underline) style.textDecoration = 'underline';

        return Object.keys(style).length > 0 ? (
          <span key={idx} style={style}>
            {seg.text}
          </span>
        ) : (
          seg.text
        );
      })}
    </>
  );
}
