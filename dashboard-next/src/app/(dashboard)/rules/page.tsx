'use client';

import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { ShieldAlert, Plus, Trash2, Power } from 'lucide-react';

interface Rule { id: string; name: string; metric: string; operator: string; threshold: number; severity: string; enabled: boolean; window_seconds?: number; }

export default function RulesPage() {
  const { data, loading, refetch } = useApi<{ rules: Rule[] }>('/api/rules');
  const rules = data?.rules || [];
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ id: '', name: '', metric: 'cpu_percent', operator: '>', threshold: '90', severity: 'high' });

  const toggle = async (id: string, enabled: boolean) => {
    await api.post(`/api/rules/${id}/${enabled ? 'disable' : 'enable'}`);
    toast('info', enabled ? 'Rule disabled' : 'Rule enabled');
    refetch();
  };

  const remove = async (id: string) => {
    await api.delete(`/api/rules/${id}`);
    toast('info', 'Rule deleted');
    refetch();
  };

  const create = async () => {
    await api.post('/api/rules', { ...form, threshold: Number(form.threshold), window_seconds: 300 });
    toast('success', 'Rule created', form.name);
    setShowCreate(false);
    setForm({ id: '', name: '', metric: 'cpu_percent', operator: '>', threshold: '90', severity: 'high' });
    refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Alert Rules</h1>
          <p className="text-sm text-[var(--text3)] mt-1">{rules.length} rules configured</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold hover:bg-[var(--accent2)] transition-all">
          <Plus className="w-4 h-4" /> New Rule
        </button>
      </div>

      <Panel noPad>
        {loading ? (
          <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" /></div>
        ) : rules.length === 0 ? (
          <div className="text-center py-16 text-[var(--text3)]"><ShieldAlert className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No rules</p></div>
        ) : (
          <div className="divide-y divide-[var(--border-color)]">
            {rules.map(r => (
              <div key={r.id} className="flex items-center gap-4 px-5 py-4 hover:bg-[var(--surface2)] transition-all">
                <div className={`w-2 h-2 rounded-full ${r.enabled ? 'bg-green-400' : 'bg-zinc-600'}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold">{r.name}</div>
                  <div className="text-xs text-[var(--text3)]">{r.metric} {r.operator} {r.threshold}</div>
                </div>
                <Badge variant={r.severity}>{r.severity}</Badge>
                <button onClick={() => toggle(r.id, r.enabled)} className="p-2 rounded-lg hover:bg-[var(--surface3)] text-[var(--text3)] hover:text-[var(--text)] transition-all" title={r.enabled ? 'Disable' : 'Enable'}>
                  <Power className="w-4 h-4" />
                </button>
                <button onClick={() => remove(r.id)} className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text3)] hover:text-red-400 transition-all">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Alert Rule" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)] hover:text-[var(--text)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold hover:bg-[var(--accent2)]">Create</button></>
      }>
        <div className="space-y-4">
          {[{ k: 'id', l: 'Rule ID', p: 'e.g. high-cpu' }, { k: 'name', l: 'Name', p: 'e.g. High CPU Alert' }].map(f => (
            <div key={f.k}><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">{f.l}</label>
            <input value={form[f.k as keyof typeof form]} onChange={e => setForm({ ...form, [f.k]: e.target.value })} placeholder={f.p}
              className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]" /></div>
          ))}
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Metric</label>
            <select value={form.metric} onChange={e => setForm({ ...form, metric: e.target.value })}
              className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
              {['cpu_percent','memory_percent','disk_percent','load_1m','network_bytes_sent'].map(m => <option key={m} value={m}>{m}</option>)}
            </select></div>
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Severity</label>
            <select value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })}
              className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
              {['critical','high','medium','low'].map(s => <option key={s} value={s}>{s}</option>)}
            </select></div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Operator</label>
            <select value={form.operator} onChange={e => setForm({ ...form, operator: e.target.value })}
              className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm">
              {['>','>=','<','<=','=='].map(o => <option key={o} value={o}>{o}</option>)}
            </select></div>
            <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Threshold</label>
            <input type="number" value={form.threshold} onChange={e => setForm({ ...form, threshold: e.target.value })}
              className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
