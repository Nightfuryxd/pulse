'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { FolderKanban, Plus, Users, GitBranch } from 'lucide-react';

interface Service { id: string; name: string; description: string; tier: string; owner?: string; language?: string; status?: string; dependencies?: string[]; }

export default function CatalogPage() {
  const { data: services, refetch } = useApi<Service[]>('/api/catalog/services');
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', desc: '', tier: 'tier-2' });

  const create = async () => { await api.post('/api/catalog/services', { name: form.name, description: form.desc, tier: form.tier, tags: [] }); toast('success', 'Service added'); setShowCreate(false); refetch(); };

  const tierColors: Record<string, string> = { 'tier-0': 'critical', 'tier-1': 'high', 'tier-2': 'medium', 'tier-3': 'low' };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Service Catalog</h1><p className="text-sm text-[var(--text3)] mt-1">{(services||[]).length} services</p></div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Plus className="w-4 h-4" /> Add Service</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {(services || []).map(s => (
          <Panel key={s.id} className="hover:border-[var(--accent)]/30">
            <div className="flex items-start justify-between mb-2"><div className="text-sm font-bold">{s.name}</div><Badge variant={tierColors[s.tier] || 'default'}>{s.tier}</Badge></div>
            <div className="text-xs text-[var(--text3)] mb-3">{s.description}</div>
            <div className="flex items-center gap-3 text-xs text-[var(--text3)]">
              {s.owner && <span className="flex items-center gap-1"><Users className="w-3 h-3" />{s.owner}</span>}
              {s.language && <span>{s.language}</span>}
              {s.dependencies?.length ? <span className="flex items-center gap-1"><GitBranch className="w-3 h-3" />{s.dependencies.length} deps</span> : null}
            </div>
          </Panel>
        ))}
      </div>
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Add Service" actions={
        <><button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={create} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Create</button></>
      }><div className="space-y-4">
        <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Name</label><input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
        <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Description</label><input value={form.desc} onChange={e => setForm({...form, desc: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none" /></div>
        <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Tier</label><select value={form.tier} onChange={e => setForm({...form, tier: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm">
          {['tier-0','tier-1','tier-2'].map(t => <option key={t}>{t}</option>)}</select></div>
      </div></Modal>
    </div>
  );
}
