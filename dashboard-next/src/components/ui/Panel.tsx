'use client';

interface PanelProps {
  children: React.ReactNode;
  title?: string;
  action?: React.ReactNode;
  className?: string;
  noPad?: boolean;
}

export default function Panel({ children, title, action, className = '', noPad }: PanelProps) {
  return (
    <div className={`bg-[var(--surface)] border border-[var(--border-color)] rounded-2xl overflow-hidden animate-slide-up ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-color)]">
          <h3 className="text-sm font-bold tracking-tight text-[var(--text)]">{title}</h3>
          {action}
        </div>
      )}
      <div className={noPad ? '' : 'p-5'}>{children}</div>
    </div>
  );
}
