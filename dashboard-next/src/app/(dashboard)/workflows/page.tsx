'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Workflow, Plus, Power, Trash2, ArrowRight } from 'lucide-react';

interface WF { id: string; name: string; description: string; enabled: boolean; trigger: { type: string }; conditions: { type: string }[]; actions: { type: string }[]; last_triggered?: string; }

export default function WorkflowsPage() {
  const { data: workflows, refetch } = useApi<WF[]>('/api/workflows');
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');

  const toggle = async (id: string) => { await api.post(`/api/workflows/${id}/toggle`); refetch(); };
  const del = async (id: string) => { await api.delete(`/api/workflows/${id}`); toast('info', 'Deleted'); refetch(); };
  const create = async () => {
    await api.post('/api/workflows', { name, description: 'Custom workflow', trigger: { type: 'metric_threshold', params: { metric: 'cpu_percent', operator: '>', value: 90 } }, conditions: [{ type: 'time_window', params: { minutes: 5 } }], actions: [{ type: 'notify', params: { channel: 'slack', target: '#alerts', message: 'Threshold exceeded' } }] });
    toast('success', 'Workflow created'); setShowCreate(false); setName(''); refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Workflows</h1><p className="text-sm text-[var(--text3)] mt-1">Automated incident response</p></div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Plus className="w-4 h-4" /> New Workflow</button>
      </div>
      <div className="space-y-3">
        {(workflows || []).map(w => (
          <Panel key={w.id}>
            <div className="flex items-center gap-4">
              <div className={`w-2 h-2 rounded-full ${w.enabled ? 'bg-green-400' : 'bg-zinc-600'}`} />
              <Workflow className="w-5 h-5 text-[var(--accent2)]" />
              <div className="flex-1">
                <div className="text-sm font-bold">{w.name}</div>
                <div className="flex items-center gap-2 mt-1 text-xs text-[var(--text3)]">
                  <Badge>{w.trigger.type}</Badge><ArrowRight className="w-3 h-3" /><Badge>{w.conditions[0]?.type || 'none'}</Badge><ArrowRight className="w-3 h-3" /><Badge variant="success">{w.actions[0]?.type || 'none'}</Badge>
                </div>
              </div>
              <button onClick={() => toggle(w.id)} className="p-2 rounded-lg hover:bg-[var(--surface3)] text-[var(--text3)]"><Power className="w-4 h-4" /></button>
              <button onClick={() => del(w.id)} className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text3)] hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
            </div>
          </Panel>
        ))}
      </div>
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Workflow" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Create</button></>
      }><div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Name</label>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. CPU Alert → Slack" className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div></Modal>
    </div>
  );
}
