'use client';

import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import { ScrollText, Search } from 'lucide-react';

interface LogEntry { id: number; timestamp: string; level: string; source: string; message: string; node?: string; }

const levelColors: Record<string, string> = { ERROR: 'text-red-400', WARN: 'text-yellow-400', INFO: 'text-blue-400', DEBUG: 'text-zinc-500' };

export default function LogsPage() {
  const { data: logsResp, loading } = useApi<{ logs: LogEntry[] }>('/api/logs');
  const logs = logsResp?.logs || [];
  const [search, setSearch] = useState('');
  const filtered = logs.filter(l => !search || l.message?.toLowerCase().includes(search.toLowerCase()) || l.source?.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Log Stream</h1><p className="text-sm text-[var(--text3)] mt-1">Aggregated application logs</p></div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text3)]" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search logs..." className="pl-10 pr-4 py-2 rounded-lg bg-[var(--surface2)] border border-[var(--border-color)] text-sm text-[var(--text)] outline-none focus:border-[var(--accent)] w-64" />
        </div>
      </div>
      <Panel noPad>
        {loading ? <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" /></div>
        : <div className="font-mono text-xs max-h-[70vh] overflow-y-auto">
          {filtered.map(l => (
            <div key={l.id} className="flex gap-3 px-5 py-1.5 hover:bg-[var(--surface2)] border-b border-[var(--border-color)]/50">
              <span className="text-[var(--text3)] whitespace-nowrap">{new Date(l.timestamp).toLocaleTimeString()}</span>
              <span className={`w-12 font-bold ${levelColors[l.level] || 'text-zinc-500'}`}>{l.level}</span>
              <span className="text-[var(--accent2)] w-24 truncate">{l.source}</span>
              <span className="text-[var(--text2)] flex-1 truncate">{l.message}</span>
            </div>
          ))}
          {!filtered.length && <div className="text-center py-16 text-[var(--text3)]"><ScrollText className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No logs</p></div>}
        </div>}
      </Panel>
    </div>
  );
}
