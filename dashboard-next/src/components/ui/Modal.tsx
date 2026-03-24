'use client';

import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  width?: string;
}

export default function Modal({ open, onClose, title, children, actions, width = 'max-w-lg' }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className={`bg-[var(--surface)] border border-[var(--border2)] rounded-2xl p-8 ${width} w-full mx-4 max-h-[80vh] overflow-y-auto shadow-2xl animate-slide-up`}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-extrabold tracking-tight">{title}</h2>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--text3)] hover:bg-[var(--surface2)] hover:text-[var(--text)] transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
        {actions && (
          <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-[var(--border-color)]">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
