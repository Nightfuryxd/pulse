'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Globe, Clock, ArrowUpDown } from 'lucide-react';

interface Check { id: string; name: string; url: string; method: string; interval_seconds: number; status: string; last_response_ms: number; uptime_percent: number; last_check: string; }

export default function SyntheticPage() {
  const { data: checks } = useApi<Check[]>('/api/synthetic/checks');
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Synthetic Monitoring</h1><p className="text-sm text-[var(--text3)] mt-1">Uptime & endpoint health checks</p></div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {(checks || []).map(c => (
          <Panel key={c.id}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2"><Globe className="w-4 h-4 text-[var(--accent2)]" /><span className="text-sm font-bold">{c.name}</span></div>
              <Badge variant={c.status === 'up' ? 'success' : 'critical'} dot>{c.status}</Badge>
            </div>
            <div className="text-xs text-[var(--text3)] truncate mb-3">{c.method} {c.url}</div>
            <div className="grid grid-cols-3 gap-2">
              <div className="p-2 rounded-lg bg-[var(--surface2)] text-center"><div className="text-lg font-bold text-green-400">{c.uptime_percent}%</div><div className="text-[10px] text-[var(--text3)]">Uptime</div></div>
              <div className="p-2 rounded-lg bg-[var(--surface2)] text-center"><div className="text-lg font-bold text-[var(--accent2)]">{c.last_response_ms}ms</div><div className="text-[10px] text-[var(--text3)]">Latency</div></div>
              <div className="p-2 rounded-lg bg-[var(--surface2)] text-center"><div className="text-lg font-bold text-[var(--text2)]">{c.interval_seconds}s</div><div className="text-[10px] text-[var(--text3)]">Interval</div></div>
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}
