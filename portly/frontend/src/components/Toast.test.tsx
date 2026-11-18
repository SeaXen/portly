import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ToastProvider, useToast } from './Toast';

function Trigger() {
  const { success, error } = useToast();
  return (
    <>
      <button onClick={() => error('Boom')}>err</button>
      <button onClick={() => success('Saved')}>ok</button>
    </>
  );
}

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('Toast', () => {
  it('uses alert/status roles and theme tokens for each type', () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>
    );

    expect(document.querySelector('[aria-live="polite"]')).toBeTruthy();

    act(() => screen.getByRole('button', { name: 'err' }).click());
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Boom');
    expect(alert.getAttribute('style')).toContain('var(--danger)');

    act(() => screen.getByRole('button', { name: 'ok' }).click());
    const status = screen.getByRole('status');
    expect(status.textContent).toContain('Saved');
    expect(status.getAttribute('style')).toContain('var(--success)');

    act(() => screen.getAllByRole('button', { name: 'Close notification' })[1].click());
    expect(screen.queryByRole('status')).toBeNull();
  });
});
