'use client';

type BadgeVariant =
  | 'critical' | 'high' | 'medium' | 'low'
  | 'info' | 'success' | 'warning' | 'ok'
  | 'active' | 'resolved' | 'fired' | 'acknowledged'
  | 'default';

const variants: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/20 shadow-red-500/5',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/20 shadow-orange-500/5',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20 shadow-yellow-500/5',
  low: 'bg-blue-500/10 text-blue-400 border-blue-500/20 shadow-blue-500/5',
  info: 'bg-blue-500/10 text-blue-400 border-blue-500/20 shadow-blue-500/5',
  ok: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-emerald-500/5',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-emerald-500/5',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20 shadow-amber-500/5',
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-emerald-500/5',
  resolved: 'bg-zinc-400/10 text-zinc-400 border-zinc-400/20',
  fired: 'bg-red-500/10 text-red-400 border-red-500/20 shadow-red-500/5',
  acknowledged: 'bg-amber-500/10 text-amber-400 border-amber-500/20 shadow-amber-500/5',
  default: 'bg-[var(--accent-soft)] text-[var(--accent2)] border-[var(--accent)]/20',
};

interface BadgeProps {
  variant?: BadgeVariant | string;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
  pulse?: boolean;
  size?: 'sm' | 'md';
}

export default function Badge({
  variant = 'default',
  children,
  className = '',
  dot,
  pulse,
  size = 'sm',
}: BadgeProps) {
  const style = variants[variant] || variants.default;
  const sizeClasses = size === 'md'
    ? 'px-3 py-1.5 text-xs'
    : 'px-2.5 py-1 text-[11px]';

  return (
    <span className={`
      inline-flex items-center gap-1.5 rounded-full font-bold uppercase tracking-wide border
      shadow-sm transition-colors duration-150
      ${sizeClasses} ${style} ${className}
    `}>
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-50" />
          )}
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-current" />
        </span>
      )}
      {children}
    </span>
  );
}
