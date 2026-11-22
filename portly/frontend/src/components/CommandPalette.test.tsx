import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandPalette } from './CommandPalette';
import { AppItem } from '../types';

const app: AppItem = {
  id: 'app-1',
  source: 'host',
  name: 'grafana',
  port: 3000,
  proto: 'tcp',
  bind: '127.0.0.1',
  status: 'up',
  category_id: 'development',
  category_mode: 'auto',
  tags: [],
  pinned: false,
  hidden: false,
  sort_order: 0,
  open_url: '',
  local_only: true,
  cpu_percent: null,
  ram_mb: null,
  uptime_sec: null,
};

function renderPalette(onSwitchView = vi.fn()) {
  render(
    <CommandPalette
      isOpen
      onClose={vi.fn()}
      apps={[app]}
      onSelectApp={vi.fn()}
      onTriggerScan={vi.fn()}
      onSwitchView={onSwitchView}
      onOpenAddApp={vi.fn()}
      onToggleSafeMode={vi.fn()}
      safeMode
    />
  );
  return { input: screen.getByRole('textbox', { name: /type a command/i }), onSwitchView };
}

describe('CommandPalette selection', () => {
  it('resets the highlight to the first item when the query changes', () => {
    const { input, onSwitchView } = renderPalette();

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.change(input, { target: { value: 'switch' } });

    const items = document.querySelectorAll('.command-item');
    expect(items.length).toBeGreaterThan(0);
    expect(items[0].classList.contains('active')).toBe(true);

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSwitchView).toHaveBeenCalledWith('table');
  });
});
