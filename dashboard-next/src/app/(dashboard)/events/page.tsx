'use client';

import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { Rss, Clock } from 'lucide-react';

interface Event { id: number; type: string; severity: string; message: string; node: string; timestamp: string; }

function timeAgo(ts: string) { const m = Math.floor((Date.now() - new Date(ts).getTime()) / 60000); if (m < 1) return 'now'; if (m < 60) return `${m}m`; const h = Math.floor(m / 60); return h < 24 ? `${h}h` : `${Math.floor(h/24)}d`; }

export default function EventsPage() {
  const { data: events, loading } = useApi<Event[]>('/api/events');
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Event Feed</h1><p className="text-sm text-[var(--text3)] mt-1">Real-time infrastructure events</p></div>
      <Panel noPad>
        {loading ? <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" /></div>
        : !events?.length ? <div className="text-center py-16 text-[var(--text3)]"><Rss className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No events</p></div>
        : <div className="divide-y divide-[var(--border-color)]">{events.map(e => (
          <div key={e.id} className="flex items-center gap-4 px-5 py-3 hover:bg-[var(--surface2)]">
            <div className={`w-2 h-2 rounded-full ${e.severity==='critical'?'bg-red-400':e.severity==='high'?'bg-orange-400':e.severity==='medium'?'bg-yellow-400':'bg-blue-400'}`} />
            <div className="flex-1 min-w-0"><div className="text-sm truncate">{e.message}</div></div>
            <span className="text-xs text-[var(--text3)]">{e.node}</span>
            <Badge variant={e.type === 'alert' ? 'critical' : e.type === 'metric' ? 'info' : 'default'}>{e.type}</Badge>
            <span className="text-xs text-[var(--text3)] flex items-center gap-1"><Clock className="w-3 h-3" />{timeAgo(e.timestamp)}</span>
          </div>
        ))}</div>}
      </Panel>
    </div>
  );
}
