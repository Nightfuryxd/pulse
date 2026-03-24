'use client';
import { useState } from 'react';
import { api } from '@/lib/api';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import { Search, Play } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface ExplorerConfig { metrics: { id: string; name: string; group: string; unit: string }[]; functions: string[]; time_ranges: string[]; }
interface Series { node: string; data: { timestamp: string; value: number }[]; }
interface QueryResult { metric: string; series: Series[]; stats: { min: number; max: number; avg: number }; }

const COLORS = ['#6366f1', '#34d399', '#f87171', '#fbbf24', '#22d3ee', '#a78bfa', '#fb923c', '#f472b6'];

export default function ExplorerPage() {
  const { data: config } = useApi<ExplorerConfig>('/api/explorer/config');
  const [metric, setMetric] = useState('cpu_usage');
  const [func, setFunc] = useState('avg');
  const [range, setRange] = useState('1h');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    const r = await api.get<QueryResult>(`/api/explorer/query?metric=${metric}&func=${func}&time_range=${range}&node=all`);
    setResult(r);
    setLoading(false);
  };

  const chartData = result?.series?.[0]?.data.map((d, i) => {
    const point: Record<string, unknown> = { time: new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    result.series.forEach(s => { point[s.node] = s.data[i]?.value; });
    return point;
  }) || [];

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Metric Explorer</h1><p className="text-sm text-[var(--text3)] mt-1">Interactive metric query builder</p></div>

      <Panel>
        <div className="flex flex-wrap items-end gap-4">
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Metric</label>
          <select value={metric} onChange={e => setMetric(e.target.value)} className="bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
            {(config?.metrics || []).map(m => <option key={m.id} value={m.id}>{m.name} ({m.unit})</option>)}
          </select></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Function</label>
          <select value={func} onChange={e => setFunc(e.target.value)} className="bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
            {(config?.functions || []).map(f => <option key={f} value={f}>{f}</option>)}
          </select></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Time Range</label>
          <select value={range} onChange={e => setRange(e.target.value)} className="bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
            {(config?.time_ranges || ['15m','1h','6h','24h','7d']).map(t => <option key={t} value={t}>{t}</option>)}
          </select></div>
          <button onClick={run} disabled={loading} className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--accent)] text-white text-sm font-bold hover:bg-[var(--accent2)] disabled:opacity-50">
            <Play className="w-4 h-4" /> Run Query
          </button>
        </div>
      </Panel>

      {result && (
        <Panel title={`${result.metric} (${func})`} action={result.stats && <span className="text-xs text-[var(--text3)]">min: {result.stats.min?.toFixed(1)} · avg: {result.stats.avg?.toFixed(1)} · max: {result.stats.max?.toFixed(1)}</span>}>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="time" tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border-color)', borderRadius: 12, fontSize: 12 }} />
                {result.series.map((s, i) => <Line key={s.node} type="monotone" dataKey={s.node} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}
    </div>
  );
}
