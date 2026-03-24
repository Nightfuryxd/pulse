'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Phone, Users, Clock, Shield, Plus } from 'lucide-react';
import { useState } from 'react';
import Modal from '@/components/ui/Modal';

interface Schedule { id: string; name: string; rotation_type: string; current_oncall: { name: string; email: string }; members: { name: string }[]; handoff_time: string; }
interface Override { id: string; user: { name: string }; start: string; end: string; reason: string; }

export default function OnCallPage() {
  const { data: schedules, refetch } = useApi<Schedule[]>('/api/oncall/schedules');
  const { data: overrides, refetch: refetchOv } = useApi<Override[]>('/api/oncall/overrides');
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');

  const create = async () => {
    await api.post('/api/oncall/schedules', { name, rotation_type: 'weekly', handoff_time: '09:00', members: [{ name: 'Team Member 1', email: 'm1@pulse.dev' }, { name: 'Team Member 2', email: 'm2@pulse.dev' }] });
    toast('success', 'Schedule created'); setShowCreate(false); setName(''); refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">On-Call Scheduling</h1><p className="text-sm text-[var(--text3)] mt-1">Rotation management</p></div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Plus className="w-4 h-4" /> New Schedule</button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {(schedules || []).map(s => (
          <Panel key={s.id}>
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-2"><Phone className="w-5 h-5 text-[var(--accent2)]" /><div><div className="text-sm font-bold">{s.name}</div><div className="text-xs text-[var(--text3)]">{s.rotation_type} · handoff {s.handoff_time}</div></div></div>
              <Badge variant="success" dot>Active</Badge>
            </div>
            <div className="p-3 rounded-xl bg-green-500/5 border border-green-500/20 mb-3">
              <div className="text-xs font-bold text-green-400 mb-1 flex items-center gap-1"><Shield className="w-3 h-3" /> Currently On-Call</div>
              <div className="text-sm font-semibold">{s.current_oncall?.name}</div>
            </div>
            <div className="flex items-center gap-1 text-xs text-[var(--text3)]"><Users className="w-3 h-3" /> {s.members?.length || 0} members in rotation</div>
          </Panel>
        ))}
      </div>
      {(overrides || []).length > 0 && <Panel title="Active Overrides">
        <div className="space-y-2">{overrides!.map(o => (
          <div key={o.id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--surface2)]">
            <Clock className="w-4 h-4 text-yellow-400" />
            <span className="text-sm font-semibold">{o.user.name}</span>
            <span className="text-xs text-[var(--text3)] flex-1">{o.reason}</span>
          </div>
        ))}</div>
      </Panel>}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Schedule" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Create</button></>
      }><div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Schedule Name</label>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Primary Rotation" className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div></Modal>
    </div>
  );
}
