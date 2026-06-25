import { ReactNode, useEffect, useRef } from 'react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  maxWidth?: string;
}

export function Modal({
  isOpen,
  onClose,
  children,
  maxWidth = '500px',
}: ModalProps) {
  useEffect(() => {
    document.body.style.overflow = isOpen ? 'hidden' : 'unset';
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isOpen) return;
    // Move focus into the dialog — first form field only, never a button, so
    // a destructive action (e.g. Delete) is never focused by default.
    const field = dialogRef.current?.querySelector<HTMLElement>(
      'input, textarea, select'
    );
    field?.focus();
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[9999] p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        className="bg-ha-card rounded-lg shadow-ha p-6 w-full max-h-[90vh] overflow-y-auto"
        style={{ maxWidth }}
      >
        {children}
      </div>
    </div>
  );
}

export function ModalHeader({
  children,
  onClose,
}: {
  children: ReactNode;
  onClose?: () => void;
}) {
  return (
    <div className="flex justify-between items-start mb-4">
      <h3 className="m-0 text-ha-text text-lg font-semibold flex-1 text-center">
        {children}
      </h3>
      {onClose && (
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-ha-text opacity-60 hover:opacity-100 text-xl transition"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export function ModalFooter({ children }: { children: ReactNode }) {
  return <div className="flex gap-3 mt-4">{children}</div>;
}
