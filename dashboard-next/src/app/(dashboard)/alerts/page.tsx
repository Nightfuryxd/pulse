'use client';

import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Bell, Clock, Server, Filter } from 'lucide-react';

interface AlertData {
  id: number;
  severity: string;
  rule_name: string;
  message: string;
  node: string;
  created_at: string;
  status: string;
  metric?: string;
  value?: number;
  threshold?: number;
}

function timeAgo(ts: string) {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function AlertsPage() {
  const { data: alerts, loading } = useApi<AlertData[]>('/api/alerts');
  const [filter, setFilter] = useState<string>('all');

  const filtered = alerts?.filter(a => filter === 'all' || a.severity === filter) || [];
  const sevCounts = {
    critical: alerts?.filter(a => a.severity === 'critical').length || 0,
    high: alerts?.filter(a => a.severity === 'high').length || 0,
    medium: alerts?.filter(a => a.severity === 'medium').length || 0,
    low: alerts?.filter(a => a.severity === 'low').length || 0,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Alerts</h1>
          <p className="text-sm text-[var(--text3)] mt-1">{alerts?.length || 0} total alerts</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2">
        <Filter className="w-4 h-4 text-[var(--text3)]" />
        {['all', 'critical', 'high', 'medium', 'low'].map(sev => (
          <button
            key={sev}
            onClick={() => setFilter(sev)}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              filter === sev
                ? 'bg-[var(--accent-soft)] text-[var(--accent2)]'
                : 'bg-[var(--surface2)] text-[var(--text3)] hover:text-[var(--text)]'
            }`}
          >
            {sev.charAt(0).toUpperCase() + sev.slice(1)}
            {sev !== 'all' && <span className="ml-1 opacity-60">{sevCounts[sev as keyof typeof sevCounts]}</span>}
          </button>
        ))}
      </div>

      <Panel noPad>
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 text-[var(--text3)]">
            <Bell className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <div className="text-sm">No alerts found</div>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-color)]">
            {filtered.map(a => (
              <div key={a.id} className="flex items-center gap-4 px-5 py-4 hover:bg-[var(--surface2)] transition-all">
                <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                  a.severity === 'critical' ? 'bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.4)]' :
                  a.severity === 'high' ? 'bg-orange-400' :
                  a.severity === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold">{a.rule_name}</div>
                  <div className="text-xs text-[var(--text3)] mt-0.5 truncate">{a.message}</div>
                </div>
                <div className="flex items-center gap-1 text-xs text-[var(--text3)]">
                  <Server className="w-3 h-3" />
                  {a.node}
                </div>
                <Badge variant={a.severity}>{a.severity}</Badge>
                <Badge variant={a.status}>{a.status}</Badge>
                <span className="text-xs text-[var(--text3)] whitespace-nowrap flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {timeAgo(a.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
