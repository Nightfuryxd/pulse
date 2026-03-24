'use client';

import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { ScrollText, Plus, Power, Trash2 } from 'lucide-react';

interface LogRule { id: string; name: string; type: string; pattern: string; severity: string; enabled: boolean; threshold: number; window_minutes: number; match_count: number; }
interface LogAlert { id: string; rule_name: string; severity: string; sample_log: string; triggered_at: string; }

export default function LogAlertsPage() {
  const { data: rules, refetch } = useApi<LogRule[]>('/api/log-alerts/rules');
  const { data: alertsData } = useApi<{ alerts: LogAlert[] }>('/api/log-alerts/alerts');
  const alerts = alertsData?.alerts || (Array.isArray(alertsData) ? alertsData as unknown as LogAlert[] : []);
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'keyword', pattern: 'ERROR', severity: 'high', threshold: '1', window_minutes: '5' });

  const toggle = async (id: string) => { await api.post(`/api/log-alerts/rules/${id}/toggle`); refetch(); };
  const remove = async (id: string) => { await api.delete(`/api/log-alerts/rules/${id}`); toast('info', 'Rule deleted'); refetch(); };
  const create = async () => {
    await api.post('/api/log-alerts/rules', { ...form, threshold: Number(form.threshold), window_minutes: Number(form.window_minutes), tags: [] });
    toast('success', 'Log rule created'); setShowCreate(false); refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Log Alerts</h1><p className="text-sm text-[var(--text3)] mt-1">Pattern-based log monitoring</p></div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold hover:bg-[var(--accent2)]"><Plus className="w-4 h-4" /> New Rule</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <Panel title="Rules" noPad>
            <div className="divide-y divide-[var(--border-color)]">
              {(rules || []).map(r => (
                <div key={r.id} className="flex items-center gap-4 px-5 py-4 hover:bg-[var(--surface2)]">
                  <div className={`w-2 h-2 rounded-full ${r.enabled ? 'bg-green-400' : 'bg-zinc-600'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold">{r.name}</div>
                    <div className="text-xs text-[var(--text3)]">{r.type}: {r.pattern} · {r.match_count} matches</div>
                  </div>
                  <Badge variant={r.severity}>{r.severity}</Badge>
                  <Badge>{r.type}</Badge>
                  <button onClick={() => toggle(r.id)} className="p-2 rounded-lg hover:bg-[var(--surface3)] text-[var(--text3)]"><Power className="w-4 h-4" /></button>
                  <button onClick={() => remove(r.id)} className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text3)] hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          </Panel>
        </div>
        <Panel title="Recent Alerts">
          <div className="space-y-2">
            {alerts.slice(0, 8).map(a => (
              <div key={a.id} className="p-3 rounded-xl bg-[var(--surface2)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold">{a.rule_name}</span>
                  <Badge variant={a.severity}>{a.severity}</Badge>
                </div>
                <div className="text-[11px] text-[var(--text3)] mt-1 truncate">{a.sample_log}</div>
              </div>
            ))}
            {alerts.length === 0 && <div className="text-sm text-[var(--text3)] text-center py-8">No alerts fired</div>}
          </div>
        </Panel>
      </div>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Log Alert Rule" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Create</button></>
      }>
        <div className="space-y-4">
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Rule Name</label>
          <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Type</label>
            <select value={form.type} onChange={e => setForm({...form, type: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
              {['keyword','regex','rate','absence'].map(t => <option key={t}>{t}</option>)}</select></div>
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Severity</label>
            <select value={form.severity} onChange={e => setForm({...form, severity: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
              {['critical','high','medium','low','info'].map(s => <option key={s}>{s}</option>)}</select></div>
          </div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Pattern</label>
          <input value={form.pattern} onChange={e => setForm({...form, pattern: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Threshold</label>
            <input type="number" value={form.threshold} onChange={e => setForm({...form, threshold: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm outline-none" /></div>
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Window (min)</label>
            <input type="number" value={form.window_minutes} onChange={e => setForm({...form, window_minutes: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm outline-none" /></div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
