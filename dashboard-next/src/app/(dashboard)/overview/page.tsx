'use client';

import { useApi } from '@/hooks/useApi';
import StatCard from '@/components/ui/StatCard';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Server, Bell, AlertTriangle, Activity, Clock, Cpu, HardDrive, Wifi } from 'lucide-react';

interface NodeData {
  hostname: string;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  status: string;
  os: string;
  last_seen: string;
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

export default function OverviewPage() {
  const { data: nodes } = useApi<NodeData[]>('/api/nodes');
  const { data: alerts } = useApi<AlertData[]>('/api/alerts');
  const { data: incidents } = useApi<IncidentData[]>('/api/incidents');

  const nodeCount = nodes?.length || 0;
  const onlineNodes = nodes?.filter(n => n.status === 'online').length || 0;
  const alertCount = alerts?.length || 0;
  const critAlerts = alerts?.filter(a => a.severity === 'critical').length || 0;
  const incidentCount = incidents?.length || 0;
  const openIncidents = incidents?.filter(i => i.status !== 'resolved').length || 0;
  const avgCpu = nodes?.length ? Math.round(nodes.reduce((s, n) => s + n.cpu_percent, 0) / nodes.length) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Overview</h1>
        <p className="text-sm text-[var(--text3)] mt-1">Infrastructure health at a glance</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Nodes" value={nodeCount} sub={`${onlineNodes} online`} icon={Server} color="#34d399" />
        <StatCard label="Active Alerts" value={alertCount} sub={`${critAlerts} critical`} icon={Bell} color="#f87171" />
        <StatCard label="Incidents" value={incidentCount} sub={`${openIncidents} open`} icon={AlertTriangle} color="#fbbf24" />
        <StatCard label="Avg CPU" value={`${avgCpu}%`} icon={Cpu} color="#6366f1" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Alerts */}
        <Panel title="Recent Alerts" action={<Badge variant="critical" dot>{alertCount}</Badge>}>
          <div className="space-y-2">
            {alerts?.slice(0, 5).map(a => (
              <div key={a.id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)] hover:bg-[var(--surface3)] transition-all">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  a.severity === 'critical' ? 'bg-red-400' : a.severity === 'high' ? 'bg-orange-400' : a.severity === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate">{a.rule_name}</div>
                  <div className="text-xs text-[var(--text3)] truncate">{a.message}</div>
                </div>
                <Badge variant={a.severity}>{a.severity}</Badge>
                <span className="text-xs text-[var(--text3)] whitespace-nowrap flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {timeAgo(a.created_at)}
                </span>
              </div>
            )) || <div className="text-sm text-[var(--text3)]">No alerts</div>}
          </div>
        </Panel>

        {/* Nodes */}
        <Panel title="Node Health" action={<Badge variant="success" dot>{onlineNodes}/{nodeCount}</Badge>}>
          <div className="space-y-2">
            {nodes?.slice(0, 5).map(n => (
              <div key={n.hostname} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)] hover:bg-[var(--surface3)] transition-all">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${n.status === 'online' ? 'bg-green-400' : 'bg-zinc-500'}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold">{n.hostname}</div>
                  <div className="text-xs text-[var(--text3)]">{n.os}</div>
                </div>
                <div className="flex items-center gap-4 text-xs text-[var(--text2)]">
                  <span className="flex items-center gap-1"><Cpu className="w-3 h-3" />{n.cpu_percent}%</span>
                  <span className="flex items-center gap-1"><Activity className="w-3 h-3" />{n.memory_percent}%</span>
                  <span className="flex items-center gap-1"><HardDrive className="w-3 h-3" />{n.disk_percent}%</span>
                </div>
              </div>
            )) || <div className="text-sm text-[var(--text3)]">No nodes</div>}
          </div>
        </Panel>
      </div>

      {/* Incidents */}
      <Panel title="Recent Incidents" action={<Badge variant={openIncidents ? 'warning' : 'success'} dot>{openIncidents ? `${openIncidents} open` : 'All clear'}</Badge>}>
        <div className="space-y-2">
          {incidents?.slice(0, 5).map(i => (
            <div key={i.id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)] hover:bg-[var(--surface3)] transition-all">
              <AlertTriangle className={`w-4 h-4 flex-shrink-0 ${
                i.severity === 'critical' ? 'text-red-400' : i.severity === 'high' ? 'text-orange-400' : 'text-yellow-400'
              }`} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold">INC-{i.id}: {i.title}</div>
              </div>
              <Badge variant={i.status}>{i.status}</Badge>
              <Badge variant={i.severity}>{i.severity}</Badge>
              <span className="text-xs text-[var(--text3)]">{timeAgo(i.created_at)}</span>
            </div>
          )) || <div className="text-sm text-[var(--text3)]">No incidents</div>}
        </div>
      </Panel>
    </div>
  );
}
