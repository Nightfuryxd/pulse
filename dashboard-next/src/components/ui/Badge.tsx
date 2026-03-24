'use client';

const variants: Record<string, string> = {
  critical: 'bg-red-400/10 text-red-400 border-red-400/20',
  high: 'bg-orange-400/10 text-orange-400 border-orange-400/20',
  medium: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/20',
  low: 'bg-blue-400/10 text-blue-400 border-blue-400/20',
  info: 'bg-zinc-400/10 text-zinc-400 border-zinc-400/20',
  success: 'bg-green-400/10 text-green-400 border-green-400/20',
  warning: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/20',
  active: 'bg-green-400/10 text-green-400 border-green-400/20',
  resolved: 'bg-zinc-400/10 text-zinc-400 border-zinc-400/20',
  fired: 'bg-red-400/10 text-red-400 border-red-400/20',
  acknowledged: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/20',
  default: 'bg-[var(--accent-soft)] text-[var(--accent2)] border-[var(--accent)]/20',
};

interface BadgeProps {
  variant?: string;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

export default function Badge({ variant = 'default', children, className = '', dot }: BadgeProps) {
  const style = variants[variant] || variants.default;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wide border ${style} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full bg-current`} />}
      {children}
    </span>
  );
}
