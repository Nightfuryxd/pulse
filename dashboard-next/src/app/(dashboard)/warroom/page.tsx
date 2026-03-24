'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Swords, Clock, Users, MessageSquare, Plus, Send, CheckCircle } from 'lucide-react';

interface WarRoom { id: string; title: string; severity: string; status: string; started_at: string; event_count: number; responders: { name: string; role: string }[]; }
interface TimelineEvent { id: string; type: string; ts: string; title: string; detail: string; actor: string; severity: string; }
interface WarRoomDetail extends WarRoom { timeline: TimelineEvent[]; notes: string; }

const evtColors: Record<string, string> = { alert: 'bg-red-400', metric_spike: 'bg-orange-400', log_pattern: 'bg-yellow-400', responder_action: 'bg-blue-400', status_change: 'bg-green-400', communication: 'bg-[var(--accent)]', rca_update: 'bg-purple-400', deployment: 'bg-cyan-400', escalation: 'bg-pink-400', runbook_step: 'bg-emerald-400' };

function timeAgo(ts: string) { const m = Math.floor((Date.now() - new Date(ts).getTime()) / 60000); return m < 60 ? `${m}m ago` : `${Math.floor(m/60)}h ago`; }

export default function WarRoomPage() {
  const { data: rooms, refetch } = useApi<WarRoom[]>('/api/warroom');
  const { toast } = useToast();
  const [detail, setDetail] = useState<WarRoomDetail | null>(null);
  const [msg, setMsg] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', severity: 'critical' });

  const open = async (id: string) => { const r = await api.get<WarRoomDetail>(`/api/warroom/${id}`); setDetail(r); };

  const postMsg = async () => {
    if (!msg.trim() || !detail) return;
    await api.post(`/api/warroom/${detail.id}/events`, { type: 'communication', title: msg, actor: 'User' });
    setMsg(''); open(detail.id);
  };

  const resolve = async () => {
    if (!detail) return;
    await api.post(`/api/warroom/${detail.id}/resolve`, { notes: '' });
    toast('success', 'Incident resolved'); setDetail(null); refetch();
  };

  const create = async () => {
    await api.post('/api/warroom', { title: form.title, severity: form.severity, commander: { name: 'Admin', email: 'admin@pulse.dev' } });
    toast('success', 'War room created'); setShowCreate(false); refetch();
  };

  if (detail) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div><button onClick={() => setDetail(null)} className="text-xs text-[var(--accent2)] hover:underline mb-1">← Back to war rooms</button>
          <h1 className="text-2xl font-extrabold tracking-tight">{detail.title}</h1>
          <div className="flex items-center gap-2 mt-1"><Badge variant={detail.severity}>{detail.severity}</Badge><Badge variant={detail.status} dot>{detail.status}</Badge><span className="text-xs text-[var(--text3)]">{timeAgo(detail.started_at)}</span></div></div>
          {detail.status === 'active' && <button onClick={resolve} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-500 text-white text-sm font-bold"><CheckCircle className="w-4 h-4" /> Resolve</button>}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div className="lg:col-span-3">
            <Panel title="Timeline" noPad>
              <div className="divide-y divide-[var(--border-color)] max-h-[60vh] overflow-y-auto">
                {detail.timeline.map(e => (
                  <div key={e.id} className="flex items-start gap-3 px-5 py-3">
                    <div className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${evtColors[e.type] || 'bg-zinc-500'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold">{e.title}</div>
                      {e.detail && <div className="text-xs text-[var(--text3)] mt-0.5">{e.detail}</div>}
                    </div>
                    <span className="text-[11px] text-[var(--text3)]">{e.actor}</span>
                    <span className="text-[11px] text-[var(--text3)]">{timeAgo(e.ts)}</span>
                  </div>
                ))}
              </div>
              {detail.status === 'active' && <div className="flex gap-2 p-4 border-t border-[var(--border-color)]">
                <input value={msg} onChange={e => setMsg(e.target.value)} onKeyDown={e => e.key === 'Enter' && postMsg()} placeholder="Post an update..." className="flex-1 bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2 text-sm outline-none focus:border-[var(--accent)]" />
                <button onClick={postMsg} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Send className="w-4 h-4" /></button>
              </div>}
            </Panel>
          </div>
          <Panel title="Responders">
            <div className="space-y-2">{detail.responders?.map((r, i) => (
              <div key={i} className="p-2 rounded-lg bg-[var(--surface2)]"><div className="text-sm font-semibold">{r.name}</div><div className="text-[11px] text-[var(--text3)]">{r.role}</div></div>
            ))}</div>
          </Panel>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">War Room</h1><p className="text-sm text-[var(--text3)] mt-1">Incident collaboration</p></div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Plus className="w-4 h-4" /> New War Room</button>
      </div>
      <div className="space-y-3">
        {(rooms || []).map(r => (
          <div key={r.id} onClick={() => open(r.id)} className="cursor-pointer">
          <Panel className="hover:border-[var(--accent)]/30">
            <div className="flex items-center gap-4">
              <Swords className={`w-5 h-5 ${r.status === 'active' ? 'text-red-400' : 'text-zinc-500'}`} />
              <div className="flex-1"><div className="text-sm font-bold">{r.title}</div><div className="flex items-center gap-2 mt-1 text-xs text-[var(--text3)]"><Users className="w-3 h-3" />{r.responders?.length} responders · {r.event_count} events · {timeAgo(r.started_at)}</div></div>
              <Badge variant={r.severity}>{r.severity}</Badge>
              <Badge variant={r.status} dot>{r.status}</Badge>
            </div>
          </Panel>
          </div>
        ))}
      </div>
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create War Room" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Create</button></>
      }><div className="space-y-4">
        <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Title</label><input value={form.title} onChange={e => setForm({...form, title: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
        <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Severity</label><select value={form.severity} onChange={e => setForm({...form, severity: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm">
          {['critical','high','medium','low'].map(s => <option key={s}>{s}</option>)}</select></div>
      </div></Modal>
    </div>
  );
}
