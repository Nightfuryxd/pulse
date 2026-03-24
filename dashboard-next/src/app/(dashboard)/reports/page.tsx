'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { FileText, Download, Clock, Printer } from 'lucide-react';

interface Report { id: string; name: string; type: string; created_at: string; status: string; period: string; }

export default function ReportsPage() {
  const { data: reports } = useApi<Report[]>('/api/reports');

  const exportPdf = () => {
    window.print();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Reports</h1><p className="text-sm text-[var(--text3)] mt-1">Generated infrastructure reports</p></div>
        <button onClick={exportPdf} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--surface2)] text-sm font-bold text-[var(--text2)] hover:text-[var(--text)]"><Printer className="w-4 h-4" /> Export PDF</button>
      </div>
      <Panel noPad>
        <div className="divide-y divide-[var(--border-color)]">
          {(reports || []).map(r => (
            <div key={r.id} className="flex items-center gap-4 px-5 py-4 hover:bg-[var(--surface2)]">
              <FileText className="w-5 h-5 text-[var(--accent2)]" />
              <div className="flex-1"><div className="text-sm font-semibold">{r.name}</div><div className="text-xs text-[var(--text3)]">{r.type} · {r.period}</div></div>
              <Badge variant={r.status === 'ready' ? 'success' : 'info'}>{r.status}</Badge>
              <span className="text-xs text-[var(--text3)] flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(r.created_at).toLocaleDateString()}</span>
              <button className="p-2 rounded-lg hover:bg-[var(--surface3)] text-[var(--text3)]"><Download className="w-4 h-4" /></button>
            </div>
          ))}
          {!reports?.length && <div className="text-center py-16 text-[var(--text3)]"><FileText className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No reports</p></div>}
        </div>
      </Panel>
    </div>
  );
}
