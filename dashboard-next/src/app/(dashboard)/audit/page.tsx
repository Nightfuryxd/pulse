'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import StatCard from '@/components/ui/StatCard';
import { FileText, Clock, Activity, User } from 'lucide-react';

interface AuditEntry { id: string; actor: string; actor_name?: string; action: string; category: string; description: string; resource?: string; resource_id?: string; ip_address?: string; created_at: string; }
interface AuditData { entries: AuditEntry[]; }
interface AuditSummary { total_entries: number; last_24h: number; last_7d: number; top_actors?: { actor: string }[]; }

const catColors: Record<string, string> = { auth: 'text-blue-400', config: 'text-yellow-400', alert: 'text-red-400', user: 'text-green-400', system: 'text-zinc-400', integration: 'text-purple-400' };

function timeAgo(ts: string) { const m = Math.floor((Date.now() - new Date(ts).getTime()) / 60000); if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`; if (m < 1440) return `${Math.floor(m / 60)}h ago`; return `${Math.floor(m / 1440)}d ago`; }

export default function AuditPage() {
  const [category, setCategory] = useState('');
  const [action, setAction] = useState('');
  const queryStr = `${category ? '&category=' + category : ''}${action ? '&action=' + action : ''}`;
  const { data: auditData } = useApi<AuditData>(`/api/audit?limit=50${queryStr}`);
  const { data: summary } = useApi<AuditSummary>('/api/audit/summary');

  const entries = auditData?.entries || [];

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Audit Log</h1><p className="text-sm text-[var(--text3)] mt-1">Activity and compliance tracking</p></div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Entries" value={summary?.total_entries ?? 0} icon={FileText} color="var(--accent2)" />
        <StatCard label="Last 24h" value={summary?.last_24h ?? 0} icon={Clock} color="#22c55e" />
        <StatCard label="Last 7 Days" value={summary?.last_7d ?? 0} icon={Activity} color="#06b6d4" />
        <StatCard label="Top Actor" value={summary?.top_actors?.[0]?.actor || '—'} icon={User} color="#a855f7" />
      </div>

      <div className="flex gap-2">
        <select value={category} onChange={e => setCategory(e.target.value)} className="bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm">
          <option value="">All Categories</option>
          {['auth', 'config', 'alert', 'user', 'system', 'integration'].map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={action} onChange={e => setAction(e.target.value)} className="bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm">
          <option value="">All Actions</option>
          {['create', 'update', 'delete', 'login', 'logout', 'invite', 'export'].map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      <Panel noPad>
        <div className="divide-y divide-[var(--border-color)]">
          {entries.map(e => (
            <div key={e.id} className="flex items-start gap-3 px-5 py-3 hover:bg-[var(--surface2)] transition-colors">
              <div className={`w-8 h-8 rounded-lg bg-[var(--surface2)] flex items-center justify-center flex-shrink-0 mt-0.5`}>
                <Activity className={`w-4 h-4 ${catColors[e.category] || 'text-zinc-400'}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-bold">{e.actor_name || e.actor}</span>
                  <Badge>{e.action}</Badge>
                  <Badge variant="default">{e.category}</Badge>
                </div>
                <div className="text-xs text-[var(--text2)] mt-1">{e.description}</div>
                {e.resource_id && <div className="text-[10px] text-[var(--text3)] mt-0.5 font-mono">{e.resource}: {e.resource_id}</div>}
              </div>
              <div className="flex-shrink-0 text-right">
                <div className="text-[10px] text-[var(--text3)]">{timeAgo(e.created_at)}</div>
                {e.ip_address && <div className="text-[9px] text-[var(--text3)] mt-0.5 font-mono">{e.ip_address}</div>}
              </div>
            </div>
          ))}
          {entries.length === 0 && <div className="p-8 text-center text-sm text-[var(--text3)]">No audit entries found</div>}
        </div>
      </Panel>
    </div>
  );
}
