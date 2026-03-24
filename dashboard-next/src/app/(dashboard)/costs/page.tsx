'use client';
import Panel from '@/components/ui/Panel';
import StatCard from '@/components/ui/StatCard';
import { DollarSign, TrendingUp, TrendingDown, Server, BarChart3 } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from 'recharts';

interface CostSummary { total_month: number; total_prev_month: number; projected: number; daily_avg: number; top_services: { name: string; cost: number; change: number }[]; by_category: { category: string; cost: number; percent: number }[]; daily: { date: string; compute: number; storage: number; network: number; other: number }[]; }

export default function CostsPage() {
  // Generate mock cost data (cost monitoring endpoint would provide real data)
  const mockCosts: CostSummary = {
    total_month: 2847,
    total_prev_month: 2650,
    projected: 3100,
    daily_avg: 95,
    top_services: [
      { name: 'Kubernetes Cluster', cost: 1200, change: 5.2 },
      { name: 'Database (RDS)', cost: 680, change: -2.1 },
      { name: 'Load Balancers', cost: 320, change: 0 },
      { name: 'Storage (S3)', cost: 280, change: 12.5 },
      { name: 'Monitoring', cost: 195, change: 3.8 },
      { name: 'CDN / Network', cost: 172, change: -5.4 },
    ],
    by_category: [
      { category: 'Compute', cost: 1520, percent: 53 },
      { category: 'Storage', cost: 560, percent: 20 },
      { category: 'Network', cost: 420, percent: 15 },
      { category: 'Other', cost: 347, percent: 12 },
    ],
    daily: Array.from({ length: 14 }, (_, i) => {
      const d = new Date(); d.setDate(d.getDate() - 13 + i);
      return {
        date: `${d.getMonth() + 1}/${d.getDate()}`,
        compute: 40 + Math.random() * 20,
        storage: 15 + Math.random() * 8,
        network: 10 + Math.random() * 10,
        other: 5 + Math.random() * 5,
      };
    }),
  };

  const data = mockCosts;
  const monthChange = ((data.total_month - data.total_prev_month) / data.total_prev_month * 100).toFixed(1);

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Cost Monitoring</h1><p className="text-sm text-[var(--text3)] mt-1">Infrastructure spend tracking</p></div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="This Month" value={`$${data.total_month.toLocaleString()}`} icon={DollarSign} color="#6366f1" trend={{ value: parseFloat(monthChange), label: 'vs last month' }} />
        <StatCard label="Last Month" value={`$${data.total_prev_month.toLocaleString()}`} icon={BarChart3} color="#71717a" />
        <StatCard label="Projected" value={`$${data.projected.toLocaleString()}`} icon={TrendingUp} color="#f59e0b" />
        <StatCard label="Daily Avg" value={`$${data.daily_avg}`} icon={Server} color="#22c55e" />
      </div>

      <Panel title="Daily Spend Breakdown">
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.daily}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }} formatter={(v) => `$${Number(v).toFixed(0)}`} />
              <Legend />
              <Bar dataKey="compute" stackId="a" fill="#6366f1" name="Compute" radius={[0, 0, 0, 0]} />
              <Bar dataKey="storage" stackId="a" fill="#34d399" name="Storage" />
              <Bar dataKey="network" stackId="a" fill="#fbbf24" name="Network" />
              <Bar dataKey="other" stackId="a" fill="#71717a" name="Other" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Top Services by Cost">
          <div className="space-y-2">
            {data.top_services.map(s => (
              <div key={s.name} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)]">
                <div className="flex-1">
                  <div className="text-sm font-semibold">{s.name}</div>
                </div>
                <span className="text-sm font-bold">${s.cost}</span>
                <span className={`text-xs font-bold flex items-center gap-0.5 ${s.change > 0 ? 'text-red-400' : s.change < 0 ? 'text-green-400' : 'text-zinc-400'}`}>
                  {s.change > 0 ? <TrendingUp className="w-3 h-3" /> : s.change < 0 ? <TrendingDown className="w-3 h-3" /> : null}
                  {s.change > 0 ? '+' : ''}{s.change}%
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Cost by Category">
          <div className="space-y-3">
            {data.by_category.map(c => (
              <div key={c.category}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-semibold">{c.category}</span>
                  <span className="text-xs text-[var(--text3)]">${c.cost} ({c.percent}%)</span>
                </div>
                <div className="h-2 bg-[var(--surface2)] rounded-full overflow-hidden">
                  <div className="h-full bg-[var(--accent)] rounded-full transition-all" style={{ width: `${c.percent}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
