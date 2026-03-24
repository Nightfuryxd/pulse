'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import StatCard from '@/components/ui/StatCard';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Server, Globe, AlertTriangle, Star } from 'lucide-react';

interface Env { id: string; name: string; description?: string; status: string; region?: string; cluster?: string; node_count: number; alert_count: number; is_default: boolean; color: string; icon?: string; }
interface EnvSummary { total: number; total_nodes: number; total_alerts: number; default?: string; }

const statusColors: Record<string, string> = { healthy: 'text-green-400', degraded: 'text-yellow-400', down: 'text-red-400', standby: 'text-purple-400' };
const statusDot: Record<string, string> = { healthy: 'bg-green-400', degraded: 'bg-yellow-400', down: 'bg-red-400', standby: 'bg-purple-400' };

export default function EnvironmentsPage() {
  const { data: envs, refetch } = useApi<Env[]>('/api/environments');
  const { data: summary } = useApi<EnvSummary>('/api/environments/summary');
  const { toast } = useToast();

  const setDefault = async (id: string) => {
    await api.post(`/api/environments/${id}/set-default`, {});
    toast('success', 'Default environment set');
    refetch();
  };

  const deleteEnv = async (id: string) => {
    await api.delete(`/api/environments/${id}`);
    toast('info', 'Environment deleted');
    refetch();
  };

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Environments</h1><p className="text-sm text-[var(--text3)] mt-1">Multi-environment management</p></div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Environments" value={summary?.total ?? 0} icon={Globe} color="var(--accent2)" />
        <StatCard label="Total Nodes" value={summary?.total_nodes ?? 0} icon={Server} color="#22c55e" />
        <StatCard label="Total Alerts" value={summary?.total_alerts ?? 0} icon={AlertTriangle} color="#eab308" />
        <StatCard label="Default" value={summary?.default || '—'} icon={Star} color="#06b6d4" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {(envs || []).map(e => (
          <Panel key={e.id}>
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: `${e.color}15` }}>
                  <Server className="w-5 h-5" style={{ color: e.color }} />
                </div>
                <div>
                  <div className="text-base font-extrabold">{e.name}</div>
                  {e.description && <div className="text-[11px] text-[var(--text3)] mt-0.5">{e.description}</div>}
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${statusDot[e.status] || 'bg-zinc-500'}`} />
                <span className={`text-[11px] font-semibold capitalize ${statusColors[e.status] || 'text-zinc-400'}`}>{e.status}</span>
                {e.is_default && <Badge variant="info" className="ml-1">Default</Badge>}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs mb-4">
              <div><span className="text-[var(--text3)]">Region:</span> <strong>{e.region || '—'}</strong></div>
              <div><span className="text-[var(--text3)]">Cluster:</span> <strong>{e.cluster || '—'}</strong></div>
              <div><span className="text-[var(--text3)]">Nodes:</span> <strong className="text-green-400">{e.node_count || 0}</strong></div>
              <div><span className="text-[var(--text3)]">Alerts:</span> <strong className={e.alert_count ? 'text-yellow-400' : ''}>{e.alert_count || 0}</strong></div>
            </div>

            {!e.is_default && (
              <div className="flex gap-2">
                <button onClick={() => setDefault(e.id)} className="text-xs px-3 py-1.5 rounded-lg bg-[var(--surface2)] font-bold text-[var(--text2)] hover:text-[var(--text)]">Set Default</button>
                <button onClick={() => deleteEnv(e.id)} className="text-xs px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 font-bold hover:bg-red-500/20">Delete</button>
              </div>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}
