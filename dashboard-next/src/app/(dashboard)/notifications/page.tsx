'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import StatCard from '@/components/ui/StatCard';
import { api } from '@/lib/api';
import { Bell, AlertTriangle, Phone, Rocket, Info, Shield } from 'lucide-react';

interface Notification { id: string; type: string; title: string; body?: string; severity: string; read: boolean; created_at: string; }
interface NotifSummary { total_unread: number; total: number; }

const typeIcons: Record<string, typeof Bell> = { alert: Bell, incident: AlertTriangle, oncall: Phone, deployment: Rocket, system: Info, security: Shield };
const typeColors: Record<string, string> = { alert: 'text-red-400', incident: 'text-yellow-400', oncall: 'text-[var(--accent)]', deployment: 'text-green-400', system: 'text-zinc-400', security: 'text-orange-400' };
const sevColors: Record<string, string> = { critical: 'text-red-400', high: 'text-yellow-400', medium: 'text-cyan-400', low: 'text-green-400', info: 'text-zinc-400' };

function timeAgo(ts: string) { const m = Math.floor((Date.now() - new Date(ts).getTime()) / 60000); if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`; if (m < 1440) return `${Math.floor(m / 60)}h ago`; return `${Math.floor(m / 1440)}d ago`; }

export default function NotificationsPage() {
  const { data: notifs, refetch } = useApi<Notification[]>('/api/notifications?limit=50');
  const { data: summary } = useApi<NotifSummary>('/api/notifications/summary');

  const markRead = async (id: string) => {
    await api.put(`/api/notifications/${id}/read`, {});
    refetch();
  };

  const markAllRead = async () => {
    await api.put('/api/notifications/read-all', {});
    refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Notifications</h1><p className="text-sm text-[var(--text3)] mt-1">All activity and alerts</p></div>
        {(summary?.total_unread || 0) > 0 && (
          <button onClick={markAllRead} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)] hover:text-[var(--text)]">Mark All Read</button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <StatCard label="Unread" value={summary?.total_unread ?? 0} icon={Bell} color="var(--accent2)" />
        <StatCard label="Total" value={summary?.total ?? 0} icon={Info} color="var(--text3)" />
      </div>

      <Panel noPad>
        <div className="divide-y divide-[var(--border-color)]">
          {(notifs || []).map(n => {
            const Icon = typeIcons[n.type] || Bell;
            return (
              <div key={n.id} onClick={() => !n.read && markRead(n.id)} className={`flex items-start gap-3 px-5 py-3 cursor-pointer hover:bg-[var(--surface2)] transition-colors ${n.read ? 'opacity-50' : 'bg-[var(--surface2)]/30'}`}>
                <div className="w-8 h-8 rounded-lg bg-[var(--surface2)] flex items-center justify-center flex-shrink-0">
                  <Icon className={`w-4 h-4 ${typeColors[n.type] || 'text-zinc-400'}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm ${n.read ? 'font-medium' : 'font-bold'} truncate`}>{n.title}</div>
                  {n.body && <div className="text-[11px] text-[var(--text3)] mt-0.5 truncate">{n.body}</div>}
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`text-[9px] font-bold ${sevColors[n.severity] || 'text-zinc-400'}`}>{n.severity}</span>
                    <span className="text-[10px] text-[var(--text3)]">{timeAgo(n.created_at)}</span>
                  </div>
                </div>
                {!n.read && <div className="w-2 h-2 rounded-full bg-[var(--accent)] flex-shrink-0 mt-2 shadow-[0_0_6px_var(--accent)]" />}
              </div>
            );
          })}
          {(notifs || []).length === 0 && <div className="p-8 text-center text-sm text-[var(--text3)]">No notifications</div>}
        </div>
      </Panel>
    </div>
  );
}
