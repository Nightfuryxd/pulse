'use client';

import { useState, useMemo, useCallback } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { Bell, Clock, Server, Filter, CheckCircle, X, ChevronDown, ChevronUp, Activity } from 'lucide-react';
import { api } from '@/lib/api';

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

const severityRowTint: Record<string, string> = {
  critical: 'bg-red-500/[0.03] hover:bg-red-500/[0.06]',
  high: 'bg-orange-500/[0.03] hover:bg-orange-500/[0.06]',
  medium: 'bg-amber-500/[0.02] hover:bg-amber-500/[0.04]',
  low: 'hover:bg-[var(--surface2)]',
};

export default function AlertsPage() {
  const { data: alertsResp, loading, refetch } = useApi<{ alerts: AlertData[] }>('/api/alerts', [], {
    refetchInterval: 30000,
  });
  const alerts = alertsResp?.alerts || [];
  const [filter, setFilter] = useState<string>('all');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [resolving, setResolving] = useState(false);

  const filtered = useMemo(
    () => alerts?.filter(a => filter === 'all' || a.severity === filter) || [],
    [alerts, filter],
  );

  const sevCounts = useMemo(() => ({
    critical: alerts?.filter(a => a.severity === 'critical').length || 0,
    high: alerts?.filter(a => a.severity === 'high').length || 0,
    medium: alerts?.filter(a => a.severity === 'medium').length || 0,
    low: alerts?.filter(a => a.severity === 'low').length || 0,
  }), [alerts]);

  const allSelected = filtered.length > 0 && filtered.every(a => selected.has(a.id));

  const toggleAll = useCallback(() => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map(a => a.id)));
    }
  }, [allSelected, filtered]);

  const toggleOne = useCallback((id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleBatchResolve = useCallback(async () => {
    if (selected.size === 0) return;
    setResolving(true);
    try {
      await Promise.all(
        Array.from(selected).map(id =>
          api.put(`/api/alerts/${id}`, { status: 'resolved' })
        )
      );
      setSelected(new Set());
      refetch();
    } catch {
      // Error handled by API client
    }
    setResolving(false);
  }, [selected, refetch]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Alerts</h1>
          <p className="text-sm text-[var(--text3)] mt-1">{alerts?.length || 0} total alerts</p>
        </div>
        {selected.size > 0 && (
          <button
            onClick={handleBatchResolve}
            disabled={resolving}
            className="
              flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold
              bg-emerald-500/10 text-emerald-400 border border-emerald-500/20
              hover:bg-emerald-500/20 transition-all disabled:opacity-50
            "
          >
            <CheckCircle className="w-4 h-4" />
            {resolving ? 'Resolving...' : `Resolve ${selected.size} alert${selected.size > 1 ? 's' : ''}`}
          </button>
        )}
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
          <div className="divide-y divide-[var(--border-color)]">
            {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 text-[var(--text3)]">
            <Bell className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <div className="text-sm">No alerts found</div>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-color)]">
            {/* Bulk select header */}
            <div className="flex items-center gap-4 px-5 py-2.5 bg-[var(--surface2)]/50 text-xs text-[var(--text3)] font-semibold">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                className="rounded border-[var(--border-color)] accent-[var(--accent)]"
              />
              <span className="flex-1">Alert</span>
              <span className="w-24">Node</span>
              <span className="w-20">Severity</span>
              <span className="w-20">Status</span>
              <span className="w-16 text-right">Time</span>
            </div>

            {filtered.map(a => (
              <div key={a.id}>
                <div
                  className={`flex items-center gap-4 px-5 py-4 transition-all cursor-pointer ${
                    severityRowTint[a.severity] || 'hover:bg-[var(--surface2)]'
                  }`}
                  onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(a.id)}
                    onChange={(e) => { e.stopPropagation(); toggleOne(a.id); }}
                    onClick={(e) => e.stopPropagation()}
                    className="rounded border-[var(--border-color)] accent-[var(--accent)]"
                  />
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    a.severity === 'critical' ? 'bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.4)]' :
                    a.severity === 'high' ? 'bg-orange-400' :
                    a.severity === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold">{a.rule_name}</div>
                    <div className="text-xs text-[var(--text3)] mt-0.5 truncate">{a.message}</div>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-[var(--text3)] w-24">
                    <Server className="w-3 h-3" />
                    {a.node}
                  </div>
                  <div className="w-20">
                    <Badge variant={a.severity}>{a.severity}</Badge>
                  </div>
                  <div className="w-20">
                    <Badge variant={a.status} dot pulse={a.status === 'fired'}>{a.status}</Badge>
                  </div>
                  <span className="text-xs text-[var(--text3)] whitespace-nowrap flex items-center gap-1 w-16 justify-end">
                    <Clock className="w-3 h-3" />
                    {timeAgo(a.created_at)}
                  </span>
                  {expandedId === a.id
                    ? <ChevronUp className="w-4 h-4 text-[var(--text3)]" />
                    : <ChevronDown className="w-4 h-4 text-[var(--text3)]" />
                  }
                </div>

                {/* Expanded detail view */}
                {expandedId === a.id && (
                  <div className="px-5 pb-4 pt-1 bg-[var(--surface2)]/30 border-t border-[var(--border-color)]/50">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                      <div>
                        <span className="text-[var(--text3)] block mb-1">Alert ID</span>
                        <span className="font-mono font-semibold">#{a.id}</span>
                      </div>
                      <div>
                        <span className="text-[var(--text3)] block mb-1">Node</span>
                        <span className="font-semibold">{a.node}</span>
                      </div>
                      {a.metric && (
                        <div>
                          <span className="text-[var(--text3)] block mb-1">Metric</span>
                          <span className="font-mono font-semibold flex items-center gap-1">
                            <Activity className="w-3 h-3 text-[var(--accent)]" />
                            {a.metric}
                          </span>
                        </div>
                      )}
                      {a.value !== undefined && a.threshold !== undefined && (
                        <div>
                          <span className="text-[var(--text3)] block mb-1">Value / Threshold</span>
                          <span className="font-mono font-semibold">
                            <span className={a.value > a.threshold ? 'text-red-400' : 'text-emerald-400'}>
                              {a.value}
                            </span>
                            {' / '}
                            {a.threshold}
                          </span>
                        </div>
                      )}
                      <div className="col-span-2 md:col-span-4">
                        <span className="text-[var(--text3)] block mb-1">Full Message</span>
                        <span className="text-[var(--text2)]">{a.message}</span>
                      </div>
                      <div className="col-span-2 md:col-span-4">
                        <span className="text-[var(--text3)] block mb-1">Created</span>
                        <span className="font-mono text-[var(--text2)]">{new Date(a.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                    {a.status !== 'resolved' && (
                      <div className="mt-3 flex gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            api.put(`/api/alerts/${a.id}`, { status: 'resolved' }).then(() => refetch());
                          }}
                          className="
                            flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold
                            bg-emerald-500/10 text-emerald-400 border border-emerald-500/20
                            hover:bg-emerald-500/20 transition-all
                          "
                        >
                          <CheckCircle className="w-3 h-3" /> Resolve
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            api.put(`/api/alerts/${a.id}`, { status: 'acknowledged' }).then(() => refetch());
                          }}
                          className="
                            flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold
                            bg-amber-500/10 text-amber-400 border border-amber-500/20
                            hover:bg-amber-500/20 transition-all
                          "
                        >
                          <X className="w-3 h-3" /> Acknowledge
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
