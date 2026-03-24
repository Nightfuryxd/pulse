'use client';

import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: LucideIcon;
  color?: string;
  trend?: { value: number; label: string };
}

export default function StatCard({ label, value, sub, icon: Icon, color = 'var(--accent)', trend }: StatCardProps) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border-color)] rounded-2xl p-5 animate-slide-up">
      <div className="flex items-start justify-between mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: `${color}15`, color }}
        >
          <Icon className="w-5 h-5" />
        </div>
        {trend && (
          <span className={`text-xs font-bold ${trend.value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {trend.value >= 0 ? '+' : ''}{trend.value}% {trend.label}
          </span>
        )}
      </div>
      <div className="text-2xl font-extrabold tracking-tight text-[var(--text)]">{value}</div>
      <div className="text-xs text-[var(--text3)] mt-1">{label}</div>
      {sub && <div className="text-[11px] text-[var(--text3)] mt-0.5">{sub}</div>}
    </div>
  );
}
