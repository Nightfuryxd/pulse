'use client';

import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Server, Cpu, MemoryStick, HardDrive, Clock } from 'lucide-react';

interface NodeData {
  hostname: string;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  status: string;
  os: string;
  platform: string;
  uptime_hours: number;
  ip: string;
  last_seen: string;
  agent_version: string;
}

function UsageBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="w-full h-2 rounded-full bg-[var(--surface3)] overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${Math.min(value, 100)}%`, background: color }}
      />
    </div>
  );
}

export default function NodesPage() {
  const { data: nodes, loading } = useApi<NodeData[]>('/api/nodes');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Nodes</h1>
        <p className="text-sm text-[var(--text3)] mt-1">Infrastructure fleet overview</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {nodes?.map(node => (
            <Panel key={node.hostname} className="hover:border-[var(--accent)]/30 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[var(--accent-soft)] flex items-center justify-center">
                    <Server className="w-5 h-5 text-[var(--accent2)]" />
                  </div>
                  <div>
                    <div className="text-sm font-bold">{node.hostname}</div>
                    <div className="text-xs text-[var(--text3)]">{node.ip} · {node.os}</div>
                  </div>
                </div>
                <Badge variant={node.status === 'online' ? 'success' : 'resolved'} dot>
                  {node.status}
                </Badge>
              </div>

              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--text3)] flex items-center gap-1"><Cpu className="w-3 h-3" /> CPU</span>
                    <span className={`font-bold ${node.cpu_percent > 85 ? 'text-red-400' : 'text-[var(--text2)]'}`}>{node.cpu_percent}%</span>
                  </div>
                  <UsageBar value={node.cpu_percent} color={node.cpu_percent > 85 ? '#f87171' : '#6366f1'} />
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--text3)] flex items-center gap-1"><MemoryStick className="w-3 h-3" /> Memory</span>
                    <span className={`font-bold ${node.memory_percent > 90 ? 'text-red-400' : 'text-[var(--text2)]'}`}>{node.memory_percent}%</span>
                  </div>
                  <UsageBar value={node.memory_percent} color={node.memory_percent > 90 ? '#f87171' : '#34d399'} />
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--text3)] flex items-center gap-1"><HardDrive className="w-3 h-3" /> Disk</span>
                    <span className={`font-bold ${node.disk_percent > 80 ? 'text-yellow-400' : 'text-[var(--text2)]'}`}>{node.disk_percent}%</span>
                  </div>
                  <UsageBar value={node.disk_percent} color={node.disk_percent > 80 ? '#fbbf24' : '#22d3ee'} />
                </div>
              </div>

              <div className="flex items-center justify-between mt-4 pt-3 border-t border-[var(--border-color)] text-[11px] text-[var(--text3)]">
                <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> Up {Math.round(node.uptime_hours)}h</span>
                <span>Agent {node.agent_version}</span>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
