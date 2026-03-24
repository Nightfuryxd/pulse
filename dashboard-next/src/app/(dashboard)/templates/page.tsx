'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { ListChecks, Download, Eye } from 'lucide-react';
import { useState } from 'react';
import Modal from '@/components/ui/Modal';

interface Pack { id: string; name: string; description: string; category: string; icon: string; rule_count: number; rules: { name: string; description: string; severity: string }[]; }

export default function TemplatesPage() {
  const { data: packs, refetch } = useApi<Pack[]>('/api/alert-templates');
  const { toast } = useToast();
  const [preview, setPreview] = useState<Pack | null>(null);

  const importPack = async (id: string) => {
    const r = await api.post<{ imported: number; pack: string }>(`/api/alert-templates/${id}/import`);
    toast('success', 'Pack Imported', `${r.imported} rules from "${r.pack}"`);
    refetch();
  };

  const showPreview = async (id: string) => {
    const p = await api.get<Pack>(`/api/alert-templates/${id}`);
    setPreview(p);
  };

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Alert Templates</h1><p className="text-sm text-[var(--text3)] mt-1">Pre-built alert rule packs</p></div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {(packs || []).map(p => (
          <Panel key={p.id} className="hover:border-[var(--accent)]/30">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2"><ListChecks className="w-5 h-5 text-[var(--accent2)]" /><div><div className="text-sm font-bold">{p.name}</div><div className="text-xs text-[var(--text3)]">{p.description}</div></div></div>
              <Badge>{p.category}</Badge>
            </div>
            <div className="text-xs text-[var(--text3)] mb-3">{p.rule_count} rules</div>
            <div className="flex gap-2">
              <button onClick={() => importPack(p.id)} className="flex-1 flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-bold hover:bg-[var(--accent2)]"><Download className="w-3 h-3" /> Import</button>
              <button onClick={() => showPreview(p.id)} className="px-3 py-2 rounded-lg bg-[var(--surface2)] text-xs font-bold text-[var(--text2)] hover:text-[var(--text)] flex items-center gap-1"><Eye className="w-3 h-3" /> Preview</button>
            </div>
          </Panel>
        ))}
      </div>
      <Modal open={!!preview} onClose={() => setPreview(null)} title={preview ? `Rules: ${preview.name}` : ''}>
        <div className="space-y-2">
          {preview?.rules?.map((r, i) => (
            <div key={i} className="p-3 rounded-xl bg-[var(--surface2)]">
              <div className="flex items-center gap-2"><Badge variant={r.severity}>{r.severity}</Badge><span className="text-sm font-semibold">{r.name}</span></div>
              <div className="text-xs text-[var(--text3)] mt-1">{r.description}</div>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
