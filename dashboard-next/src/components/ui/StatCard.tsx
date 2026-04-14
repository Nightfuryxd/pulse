'use client';

import { useEffect, useRef, useState } from 'react';
import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: LucideIcon;
  color?: string;
  trend?: { value: number; label: string };
}

function useAnimatedNumber(target: number, duration = 600): number {
  const [display, setDisplay] = useState(target);
  const prevRef = useRef(target);

  useEffect(() => {
    const start = prevRef.current;
    const diff = target - start;
    if (diff === 0) return;

    const startTime = performance.now();

    function tick(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + diff * eased;
      setDisplay(Math.round(current));

      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        prevRef.current = target;
      }
    }

    requestAnimationFrame(tick);
  }, [target, duration]);

  return display;
}

function SkeletonCard() {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border-color)] rounded-2xl p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-xl skeleton" />
      </div>
      <div className="h-8 w-16 skeleton mb-2" />
      <div className="h-3 w-24 skeleton mb-1" />
      <div className="h-3 w-16 skeleton" />
    </div>
  );
}

export { SkeletonCard };

export default function StatCard({ label, value, sub, icon: Icon, color = 'var(--accent)', trend }: StatCardProps) {
  const numericValue = typeof value === 'number' ? value : null;
  const animatedValue = useAnimatedNumber(numericValue ?? 0);

  return (
    <div className="
      group relative bg-[var(--surface)] border border-[var(--border-color)] rounded-2xl p-5 animate-slide-up
      transition-all duration-200 hover:shadow-lg hover:shadow-black/5 hover:-translate-y-0.5
      hover:border-[var(--accent)]/20 overflow-hidden
    ">
      {/* Gradient accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px] opacity-60 group-hover:opacity-100 transition-opacity duration-200"
        style={{ background: `linear-gradient(90deg, ${color}, transparent)` }}
      />
      <div className="flex items-start justify-between mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center transition-transform duration-200 group-hover:scale-105"
          style={{ background: `${color}15`, color }}
        >
          <Icon className="w-5 h-5" />
        </div>
        {trend && (
          <span className={`
            inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full
            ${trend.value >= 0
              ? 'text-emerald-400 bg-emerald-400/10'
              : 'text-red-400 bg-red-400/10'
            }
          `}>
            {trend.value >= 0 ? (
              <TrendingUp className="w-3 h-3" />
            ) : (
              <TrendingDown className="w-3 h-3" />
            )}
            {trend.value >= 0 ? '+' : ''}{trend.value}% {trend.label}
          </span>
        )}
      </div>
      <div className="text-2xl font-extrabold tracking-tight text-[var(--text)] tabular-nums">
        {numericValue !== null ? animatedValue : value}
      </div>
      <div className="text-xs text-[var(--text3)] mt-1">{label}</div>
      {sub && <div className="text-[11px] text-[var(--text3)] mt-0.5">{sub}</div>}
    </div>
  );
}
