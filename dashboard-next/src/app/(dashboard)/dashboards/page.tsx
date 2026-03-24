'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { useState } from 'react';
import { LayoutDashboard, Plus, Copy, Trash2, Edit3 } from 'lucide-react';

interface Dashboard { id: string; name: string; widgets: unknown[]; created_at: string; }

export default function DashboardsPage() {
  const { data: dashboards, refetch } = useApi<Dashboard[]>('/api/dashboards');
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');

  const create = async () => { await api.post('/api/dashboards', { name, widgets: [] }); toast('success', 'Dashboard created'); setShowCreate(false); setName(''); refetch(); };
  const dup = async (id: string) => { await api.post(`/api/dashboards/${id}/duplicate`); toast('info', 'Duplicated'); refetch(); };
  const del = async (id: string) => { await api.delete(`/api/dashboards/${id}`); toast('info', 'Deleted'); refetch(); };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Custom Dashboards</h1><p className="text-sm text-[var(--text3)] mt-1">Build your own views</p></div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Plus className="w-4 h-4" /> New Dashboard</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {(dashboards || []).map(d => (
          <Panel key={d.id} className="hover:border-[var(--accent)]/30">
            <div className="flex items-center gap-3 mb-3">
              <LayoutDashboard className="w-5 h-5 text-[var(--accent2)]" />
              <div className="flex-1"><div className="text-sm font-bold">{d.name}</div><div className="text-xs text-[var(--text3)]">{d.widgets.length} widgets</div></div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => dup(d.id)} className="flex-1 px-3 py-2 rounded-lg bg-[var(--surface2)] text-xs font-bold text-[var(--text2)] hover:text-[var(--text)] flex items-center justify-center gap-1"><Copy className="w-3 h-3" /> Duplicate</button>
              <button onClick={() => del(d.id)} className="px-3 py-2 rounded-lg bg-red-500/10 text-xs font-bold text-red-400 hover:bg-red-500/20"><Trash2 className="w-3 h-3" /></button>
            </div>
          </Panel>
        ))}
      </div>
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Dashboard" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Create</button></>
      }><div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Name</label>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="My Dashboard" className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div></Modal>
    </div>
  );
}
