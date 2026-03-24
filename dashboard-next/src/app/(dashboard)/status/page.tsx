'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Radio, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';

interface StatusService { id: string; name: string; status: string; description: string; group: string; uptime_90d?: number; }
interface StatusIncident { id: string; title: string; status: string; impact: string; created_at: string; updates: { message: string; status: string; timestamp: string }[]; }

const statusIcons: Record<string, typeof CheckCircle> = { operational: CheckCircle, degraded: AlertTriangle, partial_outage: AlertTriangle, major_outage: XCircle };
const statusColors: Record<string, string> = { operational: 'text-green-400', degraded: 'text-yellow-400', partial_outage: 'text-orange-400', major_outage: 'text-red-400' };

export default function StatusPage() {
  const { data: services } = useApi<StatusService[]>('/api/status/services');
  const { data: incidents } = useApi<StatusIncident[]>('/api/status/incidents');

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Status Page</h1><p className="text-sm text-[var(--text3)] mt-1">Public service health</p></div>

      <Panel title="Services">
        <div className="space-y-2">
          {(services || []).map(s => {
            const Icon = statusIcons[s.status] || CheckCircle;
            return (
              <div key={s.id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)]">
                <Icon className={`w-5 h-5 ${statusColors[s.status] || 'text-green-400'}`} />
                <div className="flex-1"><div className="text-sm font-semibold">{s.name}</div><div className="text-xs text-[var(--text3)]">{s.description}</div></div>
                <Badge variant={s.status === 'operational' ? 'success' : 'warning'}>{s.status.replace('_', ' ')}</Badge>
                {s.uptime_90d !== undefined && <span className="text-xs text-[var(--text3)]">{s.uptime_90d}% uptime</span>}
              </div>
            );
          })}
        </div>
      </Panel>

      {(incidents || []).length > 0 && <Panel title="Active Incidents">
        <div className="space-y-3">{incidents!.map(i => (
          <div key={i.id} className="p-4 rounded-xl bg-[var(--surface2)] border-l-4 border-orange-400">
            <div className="flex items-center gap-2 mb-2"><span className="text-sm font-bold">{i.title}</span><Badge variant={i.status === 'resolved' ? 'success' : 'warning'}>{i.status}</Badge></div>
            {i.updates?.map((u, idx) => <div key={idx} className="text-xs text-[var(--text3)] ml-3 mt-1">• {u.message}</div>)}
          </div>
        ))}</div>
      </Panel>}
    </div>
  );
}
