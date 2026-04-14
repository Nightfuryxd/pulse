'use client';

import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Skeleton from '@/components/ui/Skeleton';
import { AlertTriangle, Clock, Users, Zap, ExternalLink, ChevronDown, ChevronUp, Radio } from 'lucide-react';

interface IncidentData {
  id: number;
  title: string;
  severity: string;
  status: string;
  alert_count: number;
  created_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
  rca?: { root_cause?: string; confidence?: number };
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

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

const statusConfig: Record<string, { color: string; label: string }> = {
  fired: { color: 'fired', label: 'Active' },
  active: { color: 'active', label: 'Active' },
  acknowledged: { color: 'acknowledged', label: 'Acknowledged' },
  resolved: { color: 'resolved', label: 'Resolved' },
  investigating: { color: 'warning', label: 'Investigating' },
};

function IncidentTimeline({ incident }: { incident: IncidentData }) {
  const steps = [
    { label: 'Created', time: incident.created_at, done: true },
    { label: 'Acknowledged', time: incident.acknowledged_at, done: !!incident.acknowledged_at },
    { label: 'Resolved', time: incident.resolved_at, done: !!incident.resolved_at },
  ];

  return (
    <div className="flex items-center gap-0 mt-4 px-1">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center flex-1 last:flex-none">
          {/* Node */}
          <div className="flex flex-col items-center">
            <div className={`
              w-3 h-3 rounded-full border-2 transition-colors
              ${step.done
                ? 'bg-emerald-400 border-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.3)]'
                : 'bg-transparent border-[var(--border-color)]'
              }
            `} />
            <span className={`text-[10px] mt-1.5 whitespace-nowrap ${step.done ? 'text-[var(--text2)] font-semibold' : 'text-[var(--text3)]'}`}>
              {step.label}
            </span>
            {step.time && (
              <span className="text-[10px] text-[var(--text3)]">
                {formatTimestamp(step.time)}
              </span>
            )}
          </div>
          {/* Connecting line */}
          {i < steps.length - 1 && (
            <div className={`
              flex-1 h-0.5 mx-1 rounded-full transition-colors
              ${step.done && steps[i + 1].done
                ? 'bg-emerald-400/40'
                : step.done
                  ? 'bg-gradient-to-r from-emerald-400/40 to-[var(--border-color)]'
                  : 'bg-[var(--border-color)]'
              }
            `} />
          )}
        </div>
      ))}
    </div>
  );
}

export default function IncidentsPage() {
  const { data: incResp, loading } = useApi<{ incidents: IncidentData[] }>('/api/incidents', [], {
    refetchInterval: 30000,
  });
  const incidents = incResp?.incidents || [];
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const open = incidents?.filter(i => i.status !== 'resolved') || [];
  const resolved = incidents?.filter(i => i.status === 'resolved') || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Incidents</h1>
          <p className="text-sm text-[var(--text3)] mt-1">
            {open.length} open · {resolved.length} resolved
          </p>
        </div>
        {open.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20">
            <Radio className="w-3.5 h-3.5 text-red-400 animate-pulse" />
            <span className="text-xs font-bold text-red-400">{open.length} active</span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} variant="card" className="h-40" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {incidents?.map(inc => {
            const expanded = expandedId === inc.id;
            const status = statusConfig[inc.status] || statusConfig.active;

            return (
              <Panel key={inc.id} className="hover:border-[var(--accent)]/30 transition-all">
                <div
                  className="flex items-start gap-4 cursor-pointer"
                  onClick={() => setExpandedId(expanded ? null : inc.id)}
                >
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    inc.severity === 'critical' ? 'bg-red-400/10' : inc.severity === 'high' ? 'bg-orange-400/10' : 'bg-yellow-400/10'
                  }`}>
                    <AlertTriangle className={`w-5 h-5 ${
                      inc.severity === 'critical' ? 'text-red-400' : inc.severity === 'high' ? 'text-orange-400' : 'text-yellow-400'
                    }`} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-base font-bold">INC-{inc.id}</span>
                      <Badge variant={inc.severity}>{inc.severity}</Badge>
                      <Badge
                        variant={status.color}
                        dot
                        pulse={inc.status !== 'resolved'}
                      >
                        {status.label}
                      </Badge>
                    </div>
                    <div className="text-sm text-[var(--text2)] mt-1">{inc.title}</div>

                    <div className="flex items-center gap-4 mt-3 text-xs text-[var(--text3)]">
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {timeAgo(inc.created_at)}</span>
                      <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {inc.alert_count} alerts</span>
                      <a
                        href={`/incidents/${inc.id}/war-room`}
                        onClick={(e) => e.stopPropagation()}
                        className="
                          flex items-center gap-1 text-[var(--accent2)] font-bold
                          hover:text-[var(--accent)] transition-colors
                          px-2 py-0.5 rounded-md bg-[var(--accent-soft)] hover:bg-[var(--accent-soft)]/80
                        "
                      >
                        <ExternalLink className="w-3 h-3" />
                        War Room
                      </a>
                    </div>
                  </div>

                  <div className="flex-shrink-0 text-[var(--text3)]">
                    {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </div>
                </div>

                {/* Expanded section */}
                {expanded && (
                  <div className="mt-4 pt-4 border-t border-[var(--border-color)]/50">
                    {/* Timeline */}
                    <IncidentTimeline incident={inc} />

                    {/* RCA */}
                    {inc.rca?.root_cause && (
                      <div className="mt-4 p-3 rounded-lg bg-purple-500/5 border border-purple-500/20">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-purple-400 mb-1">
                          <Zap className="w-3 h-3" /> AI Root Cause Analysis
                          {inc.rca.confidence && (
                            <span className="text-[10px] opacity-70">({Math.round(inc.rca.confidence * 100)}% confidence)</span>
                          )}
                        </div>
                        <div className="text-xs text-[var(--text2)]">{inc.rca.root_cause}</div>
                      </div>
                    )}

                    {/* Detail grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-xs">
                      <div className="bg-[var(--surface2)]/50 rounded-lg p-2.5">
                        <span className="text-[var(--text3)] block mb-0.5">Created</span>
                        <span className="font-mono font-semibold">{formatTimestamp(inc.created_at)}</span>
                      </div>
                      {inc.acknowledged_at && (
                        <div className="bg-[var(--surface2)]/50 rounded-lg p-2.5">
                          <span className="text-[var(--text3)] block mb-0.5">Acknowledged</span>
                          <span className="font-mono font-semibold">{formatTimestamp(inc.acknowledged_at)}</span>
                        </div>
                      )}
                      {inc.resolved_at && (
                        <div className="bg-[var(--surface2)]/50 rounded-lg p-2.5">
                          <span className="text-[var(--text3)] block mb-0.5">Resolved</span>
                          <span className="font-mono font-semibold">{formatTimestamp(inc.resolved_at)}</span>
                        </div>
                      )}
                      <div className="bg-[var(--surface2)]/50 rounded-lg p-2.5">
                        <span className="text-[var(--text3)] block mb-0.5">Correlated Alerts</span>
                        <span className="font-bold text-sm">{inc.alert_count}</span>
                      </div>
                    </div>
                  </div>
                )}
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}
