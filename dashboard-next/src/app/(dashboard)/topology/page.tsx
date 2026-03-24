'use client';

import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Network, ArrowRight } from 'lucide-react';

interface TopoData { nodes: { id: string; type: string; status: string }[]; edges: { source: string; target: string; latency_ms: number }[]; }

export default function TopologyPage() {
  const { data, loading } = useApi<TopoData>('/api/topology');
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Service Topology</h1><p className="text-sm text-[var(--text3)] mt-1">Infrastructure dependency map</p></div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Services">
          <div className="space-y-2">
            {(data?.nodes || []).map(n => (
              <div key={n.id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)]">
                <Network className="w-4 h-4 text-[var(--accent2)]" />
                <span className="text-sm font-semibold flex-1">{n.id}</span>
                <Badge variant={n.status === 'healthy' ? 'success' : 'warning'} dot>{n.status}</Badge>
              </div>
            ))}
            {!data?.nodes?.length && !loading && <div className="text-sm text-[var(--text3)] text-center py-8">No topology data</div>}
          </div>
        </Panel>
        <Panel title="Connections">
          <div className="space-y-2">
            {(data?.edges || []).map((e, i) => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)]">
                <span className="text-sm font-semibold text-[var(--accent2)]">{e.source}</span>
                <ArrowRight className="w-4 h-4 text-[var(--text3)]" />
                <span className="text-sm font-semibold text-green-400">{e.target}</span>
                <span className="ml-auto text-xs text-[var(--text3)]">{e.latency_ms}ms</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
