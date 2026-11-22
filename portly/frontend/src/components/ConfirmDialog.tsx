import { useFocusTrap } from '../hooks/useFocusTrap';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDanger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isDanger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useFocusTrap<HTMLDivElement>(isOpen, onCancel);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(4px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-desc"
        style={{
          background: 'var(--surface-1)',
          border: '1px solid var(--border)',
          borderRadius: 14,
          padding: 24,
          maxWidth: 440,
          width: '100%',
          boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <h3 id="confirm-dialog-title" style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>
          {title}
        </h3>
        <p id="confirm-dialog-desc" style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>
          {message}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: '1px solid var(--border)',
              background: 'var(--surface-2)',
              color: 'var(--text)',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            style={{
              padding: '8px 18px',
              borderRadius: 8,
              border: 0,
              background: isDanger ? 'var(--danger)' : 'var(--accent)',
              color: '#0B1220',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
