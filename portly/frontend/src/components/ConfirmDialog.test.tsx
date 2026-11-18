import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfirmDialog } from './ConfirmDialog';

describe('ConfirmDialog', () => {
  it('has a labelled modal dialog, traps focus, and closes on Escape', () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();

    render(
      <>
        <button>Opener</button>
        <ConfirmDialog
          isOpen
          title="Delete container?"
          message="This cannot be undone."
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      </>
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-labelledby')).toBe('confirm-dialog-title');
    expect(screen.getByText('Delete container?')).toBeTruthy();

    const cancel = screen.getByRole('button', { name: 'Cancel' });
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(document.activeElement).toBe(cancel);

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('focuses the cancel button first for dangerous actions', () => {
    render(
      <ConfirmDialog isOpen isDanger title="Stop" message="Sure?" onConfirm={vi.fn()} onCancel={vi.fn()} />
    );
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel' }));
  });
});
