'use client';

import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { AlertTriangle, Clock, Users, Zap } from 'lucide-react';

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

export default function IncidentsPage() {
  const { data: incidents, loading } = useApi<IncidentData[]>('/api/incidents');

  const open = incidents?.filter(i => i.status !== 'resolved') || [];
  const resolved = incidents?.filter(i => i.status === 'resolved') || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Incidents</h1>
        <p className="text-sm text-[var(--text3)] mt-1">
          {open.length} open · {resolved.length} resolved
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-4">
          {incidents?.map(inc => (
            <Panel key={inc.id} className="hover:border-[var(--accent)]/30 transition-all">
              <div className="flex items-start gap-4">
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
                    <Badge variant={inc.status} dot>{inc.status}</Badge>
                  </div>
                  <div className="text-sm text-[var(--text2)] mt-1">{inc.title}</div>

                  {inc.rca?.root_cause && (
                    <div className="mt-3 p-3 rounded-lg bg-purple-500/5 border border-purple-500/20">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-purple-400 mb-1">
                        <Zap className="w-3 h-3" /> AI Root Cause Analysis
                        {inc.rca.confidence && (
                          <span className="text-[10px] opacity-70">({Math.round(inc.rca.confidence * 100)}% confidence)</span>
                        )}
                      </div>
                      <div className="text-xs text-[var(--text2)]">{inc.rca.root_cause}</div>
                    </div>
                  )}

                  <div className="flex items-center gap-4 mt-3 text-xs text-[var(--text3)]">
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {timeAgo(inc.created_at)}</span>
                    <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {inc.alert_count} alerts</span>
                  </div>
                </div>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
