'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Check } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';

interface Usage { plan: string; price: number; retention_days: number; period_start: string; period_end: string; users_used: number; users_limit: number; alerts_used: number; alerts_limit: number; dashboards_used: number; dashboards_limit: number; usage: Record<string, { used: number; limit: number; percent: number }>; }
interface Plan { id: string; name: string; price: number; is_current: boolean; features: string[]; }
interface DailyUsage { date: string; metrics: number; logs: number; api_calls: number; }

function fmtNum(n: number) { return n > 1000000 ? (n / 1000000).toFixed(1) + 'M' : n > 1000 ? (n / 1000).toFixed(1) + 'K' : String(n); }

export default function BillingPage() {
  const { data: usage } = useApi<Usage>('/api/billing/usage');
  const { data: plans } = useApi<Plan[]>('/api/billing/plans');
  const { data: daily } = useApi<DailyUsage[]>('/api/billing/usage/daily');
  const { toast } = useToast();

  const changePlan = async (planId: string) => {
    await api.post(`/api/billing/change-plan`, { plan_id: planId });
    toast('success', 'Plan changed');
  };

  const chartData = (daily || []).map(d => ({ date: d.date.slice(5), Metrics: d.metrics / 1000, Logs: d.logs / 1000, 'API Calls': d.api_calls / 1000 }));

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Billing & Usage</h1><p className="text-sm text-[var(--text3)] mt-1">Plan management and resource consumption</p></div>

      {usage && (
        <Panel>
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.08))', margin: '-20px', padding: '20px', borderRadius: 'inherit' }}>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--text3)]">Current Plan</div>
              <div className="text-3xl font-black text-[var(--accent2)] mt-1">{usage.plan}</div>
              <div className="text-xs text-[var(--text3)] mt-1">${usage.price}/mo · {usage.retention_days}-day retention · {usage.period_start} to {usage.period_end}</div>
            </div>
            <div className="text-xs text-[var(--text3)] space-y-1 md:text-right">
              <div>Users: <strong>{usage.users_used}/{usage.users_limit}</strong></div>
              <div>Alerts: <strong>{usage.alerts_used}/{usage.alerts_limit}</strong></div>
              <div>Dashboards: <strong>{usage.dashboards_used}/{usage.dashboards_limit}</strong></div>
            </div>
          </div>
        </Panel>
      )}

      {usage && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Object.entries(usage.usage).map(([key, m]) => {
            const barColor = m.percent > 80 ? 'bg-red-400' : m.percent > 60 ? 'bg-yellow-400' : 'bg-green-400';
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            return (
              <Panel key={key}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs font-bold">{label}</span>
                  <span className="text-[11px] text-[var(--text3)]">{fmtNum(m.used)} / {fmtNum(m.limit)}</span>
                </div>
                <div className="h-2 bg-[var(--surface2)] rounded-full overflow-hidden">
                  <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${Math.min(m.percent, 100)}%` }} />
                </div>
                <div className={`text-[10px] font-semibold mt-1 ${m.percent > 80 ? 'text-red-400' : m.percent > 60 ? 'text-yellow-400' : 'text-green-400'}`}>{m.percent}% used</div>
              </Panel>
            );
          })}
        </div>
      )}

      {daily && daily.length > 0 && (
        <Panel title="Daily Usage (K)">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} />
                <YAxis tick={{ fill: '#71717a', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }} />
                <Legend />
                <Bar dataKey="Metrics" stackId="a" fill="#6366f1" radius={[2, 2, 0, 0]} />
                <Bar dataKey="Logs" stackId="a" fill="#34d399" radius={[2, 2, 0, 0]} />
                <Bar dataKey="API Calls" stackId="a" fill="#fbbf24" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {(plans || []).map(p => (
          <Panel key={p.id} className={p.is_current ? 'border-[var(--accent)] shadow-[0_0_20px_rgba(99,102,241,0.1)]' : ''}>
            <div className="flex justify-between items-center mb-3">
              <div className="text-lg font-black">{p.name}</div>
              {p.is_current && <Badge variant="success">Current</Badge>}
            </div>
            <div className="text-3xl font-black text-[var(--accent2)]">${p.price}<span className="text-sm text-[var(--text3)] font-normal">/mo</span></div>
            <ul className="mt-3 space-y-1">
              {(p.features || []).map((f, i) => (
                <li key={i} className="text-xs text-[var(--text2)] flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-green-400" />{f}</li>
              ))}
            </ul>
            {!p.is_current && <button onClick={() => changePlan(p.id)} className="w-full mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Switch to {p.name}</button>}
          </Panel>
        ))}
      </div>
    </div>
  );
}
