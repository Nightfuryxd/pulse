'use client';

import { createContext, useCallback, useContext, useState } from 'react';
import { AlertTriangle, CheckCircle, Info, X, XCircle } from 'lucide-react';

interface Toast {
  id: number;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
}

interface ToastContextType {
  toast: (type: Toast['type'], title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextType>({ toast: () => {} });

let nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((type: Toast['type'], title: string, message?: string) => {
    const id = nextId++;
    setToasts(prev => [...prev.slice(-4), { id, type, title, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 6000);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const icons = { success: CheckCircle, error: XCircle, warning: AlertTriangle, info: Info };
  const colors = { success: 'border-green-500/30 bg-green-500/5', error: 'border-red-500/30 bg-red-500/5', warning: 'border-yellow-500/30 bg-yellow-500/5', info: 'border-[var(--accent)]/30 bg-[var(--accent)]/5' };
  const iconColors = { success: 'text-green-400', error: 'text-red-400', warning: 'text-yellow-400', info: 'text-[var(--accent2)]' };

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      <div className="fixed top-4 right-4 z-[999] space-y-2 max-w-sm">
        {toasts.map(t => {
          const Icon = icons[t.type];
          return (
            <div key={t.id} className={`flex items-start gap-3 p-4 rounded-xl border ${colors[t.type]} backdrop-blur-xl shadow-lg animate-slide-up`}>
              <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${iconColors[t.type]}`} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-[var(--text)]">{t.title}</div>
                {t.message && <div className="text-xs text-[var(--text2)] mt-0.5">{t.message}</div>}
              </div>
              <button onClick={() => dismiss(t.id)} className="text-[var(--text3)] hover:text-[var(--text)]">
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
