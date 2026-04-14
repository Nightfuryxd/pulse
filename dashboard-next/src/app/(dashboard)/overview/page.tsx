'use client';

import { useApi } from '@/hooks/useApi';
import StatCard, { SkeletonCard } from '@/components/ui/StatCard';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Server, Bell, AlertTriangle, Activity, Clock, Cpu, HardDrive } from 'lucide-react';

interface NodeMetric {
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  load_avg: number;
  net_bytes_sent: number;
  net_bytes_recv: number;
  process_count: number;
}

interface NodeData {
  id: string;
  hostname: string;
  status: string;
  os: string;
  ip: string;
  last_seen: string;
  latest_metric: NodeMetric | null;
}

interface AlertData {
  id: number;
  severity: string;
  rule_name: string;
  message: string;
  node: string;
  created_at: string;
  status: string;
}

interface IncidentData {
  id: number;
  title: string;
  severity: string;
  status: string;
  created_at: string;
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

function ListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)]">
          <div className="w-2 h-2 rounded-full skeleton" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3.5 w-3/4 skeleton" />
            <div className="h-3 w-1/2 skeleton" />
          </div>
          <div className="h-5 w-16 skeleton rounded-full" />
        </div>
      ))}
    </div>
  );
}

export default function OverviewPage() {
  const { data: nodesResp, loading: nodesLoading } = useApi<{ nodes: NodeData[] }>('/api/nodes');
  const { data: alertsResp, loading: alertsLoading } = useApi<{ alerts: AlertData[] }>('/api/alerts');
  const { data: incidentsResp, loading: incidentsLoading } = useApi<{ incidents: IncidentData[] }>('/api/incidents');

  const nodes = nodesResp?.nodes || [];
  const alerts = alertsResp?.alerts || [];
  const incidents = incidentsResp?.incidents || [];

  const nodeCount = nodes.length;
  const onlineNodes = nodes.filter(n => n.status === 'online' || n.status === 'active').length;
  const alertCount = alerts.length;
  const critAlerts = alerts.filter(a => a.severity === 'critical').length;
  const incidentCount = incidents.length;
  const openIncidents = incidents.filter(i => i.status !== 'resolved').length;
  const avgCpu = nodes.length ? Math.round(nodes.reduce((s, n) => s + (n.latest_metric?.cpu_percent || 0), 0) / nodes.length) : 0;

  const isLoading = nodesLoading || alertsLoading || incidentsLoading;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Overview</h1>
        <p className="text-sm text-[var(--text3)] mt-1">Infrastructure health at a glance</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <StatCard label="Total Nodes" value={nodeCount} sub={`${onlineNodes} online`} icon={Server} color="#34d399" />
            <StatCard label="Active Alerts" value={alertCount} sub={`${critAlerts} critical`} icon={Bell} color="#f87171" />
            <StatCard label="Incidents" value={incidentCount} sub={`${openIncidents} open`} icon={AlertTriangle} color="#fbbf24" />
            <StatCard label="Avg CPU" value={`${avgCpu}%`} icon={Cpu} color="#6366f1" />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Alerts */}
        <Panel title="Recent Alerts" action={<Badge variant="critical" dot>{alertCount}</Badge>}>
          {alertsLoading ? (
            <ListSkeleton rows={4} />
          ) : (
            <div className="space-y-2">
              {alerts?.slice(0, 5).map(a => (
                <div key={a.id} className="group flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)] hover:bg-[var(--surface3)] transition-all duration-150 cursor-pointer">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    a.severity === 'critical' ? 'bg-red-400' : a.severity === 'high' ? 'bg-orange-400' : a.severity === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold truncate group-hover:text-[var(--text)] transition-colors duration-150">{a.rule_name}</div>
                    <div className="text-xs text-[var(--text3)] truncate">{a.message}</div>
                  </div>
                  <Badge variant={a.severity}>{a.severity}</Badge>
                  <span className="text-xs text-[var(--text3)] whitespace-nowrap flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {timeAgo(a.created_at)}
                  </span>
                </div>
              )) || <div className="text-sm text-[var(--text3)] py-4 text-center">No alerts</div>}
            </div>
          )}
        </Panel>

        {/* Nodes */}
        <Panel title="Node Health" action={<Badge variant="success" dot>{onlineNodes}/{nodeCount}</Badge>}>
          {nodesLoading ? (
            <ListSkeleton rows={4} />
          ) : (
            <div className="space-y-2">
              {nodes?.slice(0, 5).map(n => (
                <div key={n.hostname} className="group flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)] hover:bg-[var(--surface3)] transition-all duration-150 cursor-pointer">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${n.status === 'online' || n.status === 'active' ? 'bg-green-400' : 'bg-zinc-500'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold group-hover:text-[var(--text)] transition-colors duration-150">{n.hostname}</div>
                    <div className="text-xs text-[var(--text3)]">{n.os}</div>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-[var(--text2)]">
                    <span className="flex items-center gap-1"><Cpu className="w-3 h-3" />{n.latest_metric?.cpu_percent ?? '—'}%</span>
                    <span className="flex items-center gap-1"><Activity className="w-3 h-3" />{n.latest_metric?.memory_percent ?? '—'}%</span>
                    <span className="flex items-center gap-1"><HardDrive className="w-3 h-3" />{n.latest_metric?.disk_percent ?? '—'}%</span>
                  </div>
                </div>
              )) || <div className="text-sm text-[var(--text3)] py-4 text-center">No nodes</div>}
            </div>
          )}
        </Panel>
      </div>

      {/* Incidents */}
      <Panel title="Recent Incidents" action={<Badge variant={openIncidents ? 'warning' : 'success'} dot>{openIncidents ? `${openIncidents} open` : 'All clear'}</Badge>}>
        {incidentsLoading ? (
          <ListSkeleton rows={3} />
        ) : (
          <div className="space-y-2">
            {incidents?.slice(0, 5).map(i => (
              <div key={i.id} className="group flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)] hover:bg-[var(--surface3)] transition-all duration-150 cursor-pointer">
                <AlertTriangle className={`w-4 h-4 flex-shrink-0 ${
                  i.severity === 'critical' ? 'text-red-400' : i.severity === 'high' ? 'text-orange-400' : 'text-yellow-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold group-hover:text-[var(--text)] transition-colors duration-150">INC-{i.id}: {i.title}</div>
                </div>
                <Badge variant={i.status}>{i.status}</Badge>
                <Badge variant={i.severity}>{i.severity}</Badge>
                <span className="text-xs text-[var(--text3)]">{timeAgo(i.created_at)}</span>
              </div>
            )) || <div className="text-sm text-[var(--text3)] py-4 text-center">No incidents</div>}
          </div>
        )}
      </Panel>
    </div>
  );
}
