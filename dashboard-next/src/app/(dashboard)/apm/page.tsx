'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import StatCard from '@/components/ui/StatCard';
import { api } from '@/lib/api';
import { Zap, Clock, AlertTriangle, Activity, ArrowRight } from 'lucide-react';

interface Trace { trace_id: string; root_service: string; root_operation: string; start_time: string; duration_ms: number; span_count: number; has_error: boolean; status: string; services: string[]; }
interface ApmSummary { total_traces: number; error_rate: number; avg_duration_ms: number; p95_duration_ms: number; p99_duration_ms: number; }
interface ServiceMap { nodes: { id: string; type: string }[]; edges: { source: string; target: string }[]; }
interface Span { span_id: string; operation: string; service: string; duration_ms: number; depth: number; status: string; }

export default function ApmPage() {
  const { data: traces } = useApi<Trace[]>('/api/apm/traces');
  const { data: summary } = useApi<ApmSummary>('/api/apm/summary');
  const { data: svcMap } = useApi<ServiceMap>('/api/apm/service-map');
  const [selected, setSelected] = useState<{ trace_id: string; spans: Span[] } | null>(null);

  const openTrace = async (id: string) => {
    const detail = await api.get<{ trace_id: string; spans: Span[] }>(`/api/apm/traces/${id}`);
    setSelected(detail);
  };

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">APM / Distributed Tracing</h1><p className="text-sm text-[var(--text3)] mt-1">Request traces across services</p></div>
      {summary && <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Traces" value={summary.total_traces} icon={Zap} color="#6366f1" />
        <StatCard label="Error Rate" value={`${summary.error_rate}%`} icon={AlertTriangle} color="#f87171" />
        <StatCard label="Avg Duration" value={`${summary.avg_duration_ms}ms`} icon={Clock} color="#34d399" />
        <StatCard label="P99 Latency" value={`${summary.p99_duration_ms}ms`} icon={Activity} color="#fbbf24" />
      </div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <Panel title="Recent Traces" noPad>
            <div className="divide-y divide-[var(--border-color)] max-h-[60vh] overflow-y-auto">
              {(traces || []).slice(0, 30).map(t => (
                <div key={t.trace_id} onClick={() => openTrace(t.trace_id)} className="flex items-center gap-4 px-5 py-3 hover:bg-[var(--surface2)] cursor-pointer">
                  <div className={`w-2 h-2 rounded-full ${t.has_error ? 'bg-red-400' : 'bg-green-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold">{t.root_service}</div>
                    <div className="text-xs text-[var(--text3)]">{t.root_operation}</div>
                  </div>
                  <span className="text-xs text-[var(--text3)]">{t.span_count} spans</span>
                  <span className="text-xs font-bold text-[var(--text2)]">{t.duration_ms}ms</span>
                  <Badge variant={t.has_error ? 'critical' : 'success'}>{t.status}</Badge>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel title="Service Map">
          <div className="space-y-2">
            {(svcMap?.nodes || []).map(n => (
              <div key={n.id} className="p-3 rounded-xl bg-[var(--surface2)]">
                <div className="text-sm font-semibold">{n.id}</div>
                <div className="text-xs text-[var(--text3)]">{n.type}</div>
              </div>
            ))}
          </div>
          {svcMap?.edges && <div className="mt-3 space-y-1">
            {svcMap.edges.map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-[var(--text3)]">
                <span className="text-[var(--accent2)]">{e.source}</span><ArrowRight className="w-3 h-3" /><span className="text-green-400">{e.target}</span>
              </div>
            ))}
          </div>}
        </Panel>
      </div>

      {selected && (
        <Panel title={`Trace: ${selected.trace_id.slice(0, 12)}...`}>
          <div className="space-y-1">
            {selected.spans?.map(s => (
              <div key={s.span_id} className="flex items-center gap-2 py-2 hover:bg-[var(--surface2)] rounded-lg px-2" style={{ paddingLeft: `${(s.depth || 0) * 24 + 8}px` }}>
                <div className={`w-1.5 h-1.5 rounded-full ${s.status === 'error' ? 'bg-red-400' : 'bg-green-400'}`} />
                <span className="text-xs font-bold text-[var(--accent2)]">{s.service}</span>
                <span className="text-xs text-[var(--text2)] flex-1">{s.operation}</span>
                <span className="text-xs font-mono text-[var(--text3)]">{s.duration_ms}ms</span>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
