'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import StatCard from '@/components/ui/StatCard';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Users, UserPlus, Shield, UserX } from 'lucide-react';

interface UserItem { id: string; name: string; email: string; role: string; status: string; avatar_color?: string; }
interface UserSummary { total_users: number; active: number; invited: number; inactive: number; }

const roleColors: Record<string, string> = { admin: 'text-red-400', editor: 'text-blue-400', responder: 'text-yellow-400', viewer: 'text-zinc-400' };

export default function TeamPage() {
  const { data: users, refetch } = useApi<UserItem[]>('/api/users');
  const { data: summary } = useApi<UserSummary>('/api/users/summary');
  const { toast } = useToast();
  const [showInvite, setShowInvite] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', role: 'viewer' });

  const changeRole = async (id: string, role: string) => {
    await api.post(`/api/users/${id}/role`, { role });
    refetch();
  };

  const deactivate = async (id: string) => {
    await api.post(`/api/users/${id}/deactivate`, {});
    toast('info', 'User deactivated');
    refetch();
  };

  const reactivate = async (id: string) => {
    await api.post(`/api/users/${id}/reactivate`, {});
    toast('success', 'User reactivated');
    refetch();
  };

  const invite = async () => {
    await api.post('/api/users/invite', { name: form.name, email: form.email || form.name.toLowerCase().replace(/\s+/g, '.') + '@pulse.dev', role: form.role });
    toast('success', 'User invited');
    setShowInvite(false);
    setForm({ name: '', email: '', role: 'viewer' });
    refetch();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Users & Teams</h1><p className="text-sm text-[var(--text3)] mt-1">Manage team members</p></div>
        <button onClick={() => setShowInvite(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><UserPlus className="w-4 h-4" /> Invite User</button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Users" value={summary?.total_users ?? 0} icon={Users} color="var(--accent2)" />
        <StatCard label="Active" value={summary?.active ?? 0} icon={Shield} color="#22c55e" />
        <StatCard label="Invited" value={summary?.invited ?? 0} icon={UserPlus} color="#06b6d4" />
        <StatCard label="Inactive" value={summary?.inactive ?? 0} icon={UserX} color="var(--text3)" />
      </div>

      <Panel title="Members" noPad>
        <div className="divide-y divide-[var(--border-color)]">
          {(users || []).map(u => (
            <div key={u.id} className="flex items-center gap-3 px-5 py-3 hover:bg-[var(--surface2)] transition-colors">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: `${u.avatar_color || 'var(--accent)'}20`, color: u.avatar_color || 'var(--accent)' }}>
                {(u.name || u.email || '?')[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold">{u.name || '—'}</div>
                <div className="text-xs text-[var(--text3)]">{u.email}</div>
              </div>
              <span className={`text-xs font-semibold ${roleColors[u.role] || 'text-zinc-400'}`}>{u.role}</span>
              <Badge variant={u.status === 'active' ? 'success' : u.status === 'invited' ? 'info' : 'default'} dot>{u.status}</Badge>
              <select value={u.role} onChange={e => changeRole(u.id, e.target.value)} className="text-xs px-2 py-1 bg-[var(--surface2)] border border-[var(--border-color)] rounded text-[var(--text)]">
                {['admin', 'editor', 'responder', 'viewer'].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              {u.status === 'active' && <button onClick={() => deactivate(u.id)} className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-400 font-bold hover:bg-red-500/20">Deactivate</button>}
              {u.status === 'inactive' && <button onClick={() => reactivate(u.id)} className="text-xs px-2 py-1 rounded bg-[var(--surface2)] text-[var(--text2)] font-bold hover:text-[var(--text)]">Reactivate</button>}
            </div>
          ))}
        </div>
      </Panel>

      <Modal open={showInvite} onClose={() => setShowInvite(false)} title="Invite User" actions={
        <><button onClick={() => setShowInvite(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={invite} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Invite</button></>
      }>
        <div className="space-y-4">
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Full Name</label>
          <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Alex Chen" className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Email</label>
          <input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="alex@pulse.dev" className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Role</label>
          <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm">
            {['admin', 'editor', 'responder', 'viewer'].map(r => <option key={r}>{r}</option>)}
          </select></div>
        </div>
      </Modal>
    </div>
  );
}
