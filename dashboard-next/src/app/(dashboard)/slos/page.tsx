'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Gauge, TrendingDown } from 'lucide-react';

interface SLO { id: string; name: string; target: number; current: number; type: string; window_days: number; budget_remaining: number; status: string; }

export default function SlosPage() {
  const { data: slos } = useApi<SLO[]>('/api/slos');
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">SLO / SLA Tracking</h1><p className="text-sm text-[var(--text3)] mt-1">Service level objectives & error budgets</p></div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(slos || []).map(s => {
          const pct = Math.min((s.current / s.target) * 100, 100);
          const healthy = s.current >= s.target;
          return (
            <Panel key={s.id}>
              <div className="flex items-start justify-between mb-4">
                <div><div className="text-sm font-bold">{s.name}</div><div className="text-xs text-[var(--text3)]">{s.type} · {s.window_days}-day window</div></div>
                <Badge variant={healthy ? 'success' : 'critical'} dot>{s.status}</Badge>
              </div>
              <div className="flex items-end gap-4 mb-3">
                <div className="text-3xl font-extrabold" style={{ color: healthy ? '#34d399' : '#f87171' }}>{s.current}%</div>
                <div className="text-sm text-[var(--text3)] mb-1">/ {s.target}% target</div>
              </div>
              <div className="w-full h-3 rounded-full bg-[var(--surface3)] overflow-hidden mb-2">
                <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: healthy ? '#34d399' : '#f87171' }} />
              </div>
              <div className="flex justify-between text-xs text-[var(--text3)]">
                <span>Budget remaining: {s.budget_remaining}%</span>
                {!healthy && <span className="text-red-400 flex items-center gap-1"><TrendingDown className="w-3 h-3" /> Breaching</span>}
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
