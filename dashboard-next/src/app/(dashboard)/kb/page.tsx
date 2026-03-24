'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import Modal from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { BookOpen, Plus, Search, Trash2 } from 'lucide-react';

interface KbEntry { id: string; title: string; type: string; tags: string | string[]; content: string; created_at: string; }

export default function KbPage() {
  const { data, refetch } = useApi<{ entries: KbEntry[] }>('/api/kb');
  const entries = data?.entries || [];
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ title: '', type: 'runbook', tags: '', content: '' });

  const filtered = entries.filter(e => !search || e.title.toLowerCase().includes(search.toLowerCase()));
  const tags = (e: KbEntry) => Array.isArray(e.tags) ? e.tags : (typeof e.tags === 'string' && e.tags ? e.tags.split(',').map(t => t.trim()) : []);

  const save = async () => {
    await api.post('/api/kb/entries', { ...form, tags: form.tags });
    toast('success', 'Entry added'); setShowAdd(false); refetch();
  };
  const remove = async (id: string) => { await api.delete(`/api/kb/entries/${id}`); toast('info', 'Entry deleted'); refetch(); };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Knowledge Base</h1><p className="text-sm text-[var(--text3)] mt-1">{entries.length} entries</p></div>
        <div className="flex gap-3">
          <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text3)]" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search..." className="pl-10 pr-4 py-2 rounded-lg bg-[var(--surface2)] border border-[var(--border-color)] text-sm w-48 outline-none focus:border-[var(--accent)]" /></div>
          <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold"><Plus className="w-4 h-4" /> Add</button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map(e => (
          <Panel key={e.id} className="hover:border-[var(--accent)]/30">
            <div className="flex items-start justify-between mb-2">
              <div className="text-sm font-bold">{e.title}</div>
              <button onClick={() => remove(e.id)} className="p-1 rounded hover:bg-red-500/10 text-[var(--text3)] hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
            <Badge>{e.type}</Badge>
            <div className="text-xs text-[var(--text3)] mt-2 line-clamp-3">{e.content}</div>
            <div className="flex flex-wrap gap-1 mt-2">{tags(e).map(t => <span key={t} className="px-2 py-0.5 rounded-full bg-[var(--surface3)] text-[10px] text-[var(--text3)]">{t}</span>)}</div>
          </Panel>
        ))}
        {!filtered.length && <div className="col-span-full text-center py-16 text-[var(--text3)]"><BookOpen className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No entries</p></div>}
      </div>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add KB Entry" actions={
        <><button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)]">Cancel</button>
        <button onClick={save} className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Save</button></>
      }>
        <div className="space-y-4">
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Title</label>
          <input value={form.title} onChange={e => setForm({...form, title: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Type</label>
          <select value={form.type} onChange={e => setForm({...form, type: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm">
            {['runbook','incident','alert_guide','config_note'].map(t => <option key={t}>{t}</option>)}</select></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Tags (comma-separated)</label>
          <input value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Content</label>
          <textarea value={form.content} onChange={e => setForm({...form, content: e.target.value})} rows={5} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none font-mono resize-y" /></div>
        </div>
      </Modal>
    </div>
  );
}
