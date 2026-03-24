'use client';
import { useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Play, CheckCircle, Circle, Clock, BookOpen, Plus } from 'lucide-react';

interface RunbookStep { id: string; title: string; description: string; status: string; output?: string; }
interface Runbook { id: string; title: string; description: string; type: string; tags: string[]; steps: RunbookStep[]; last_run?: string; status: string; }

const stepStatusIcon: Record<string, typeof Circle> = { pending: Circle, running: Clock, completed: CheckCircle, failed: Circle };
const stepStatusColor: Record<string, string> = { pending: 'text-zinc-500', running: 'text-yellow-400 animate-pulse', completed: 'text-green-400', failed: 'text-red-400' };

export default function RunbooksPage() {
  const { data: entries } = useApi<{ entries: Runbook[] }>('/api/kb?type=runbook');
  const { toast } = useToast();
  const [active, setActive] = useState<Runbook | null>(null);
  const [steps, setSteps] = useState<RunbookStep[]>([]);

  const runbooks = entries?.entries || [];

  const openRunbook = (rb: Runbook) => {
    setActive(rb);
    setSteps((rb.steps || [
      { id: '1', title: 'Verify symptoms', description: 'Check monitoring dashboards for the reported issue', status: 'pending' },
      { id: '2', title: 'Gather logs', description: 'Collect relevant log entries from affected services', status: 'pending' },
      { id: '3', title: 'Apply fix', description: 'Execute the remediation steps', status: 'pending' },
      { id: '4', title: 'Verify resolution', description: 'Confirm the issue is resolved and metrics are normal', status: 'pending' },
    ]).map(s => ({ ...s, status: 'pending', output: '' })));
  };

  const executeStep = async (idx: number) => {
    const updated = [...steps];
    updated[idx] = { ...updated[idx], status: 'running' };
    setSteps(updated);

    // Simulate step execution
    await new Promise(r => setTimeout(r, 1500));
    updated[idx] = { ...updated[idx], status: 'completed', output: `Step "${updated[idx].title}" completed successfully at ${new Date().toLocaleTimeString()}` };
    setSteps([...updated]);
    toast('success', `Step ${idx + 1} completed`);
  };

  const executeAll = async () => {
    for (let i = 0; i < steps.length; i++) {
      if (steps[i].status !== 'completed') {
        await executeStep(i);
      }
    }
    toast('success', 'Runbook execution complete');
  };

  if (active) {
    const allDone = steps.every(s => s.status === 'completed');
    const progress = steps.filter(s => s.status === 'completed').length;
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <button onClick={() => setActive(null)} className="text-xs text-[var(--accent2)] hover:underline mb-1">← Back to runbooks</button>
            <h1 className="text-2xl font-extrabold tracking-tight">{active.title}</h1>
            <p className="text-sm text-[var(--text3)] mt-1">{active.description || 'Automated runbook execution'}</p>
          </div>
          {!allDone && (
            <button onClick={executeAll} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">
              <Play className="w-4 h-4" /> Run All Steps
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-[var(--text3)]">
          <div className="flex-1 h-2 bg-[var(--surface2)] rounded-full overflow-hidden">
            <div className="h-full bg-green-400 rounded-full transition-all duration-500" style={{ width: `${(progress / steps.length) * 100}%` }} />
          </div>
          <span className="font-bold">{progress}/{steps.length} steps</span>
        </div>

        <div className="space-y-3">
          {steps.map((step, idx) => {
            const Icon = stepStatusIcon[step.status] || Circle;
            return (
              <Panel key={step.id}>
                <div className="flex items-start gap-4">
                  <div className="flex flex-col items-center gap-1 pt-0.5">
                    <div className="w-8 h-8 rounded-full bg-[var(--surface2)] flex items-center justify-center text-xs font-bold">{idx + 1}</div>
                    {idx < steps.length - 1 && <div className="w-px h-8 bg-[var(--border-color)]" />}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Icon className={`w-4 h-4 ${stepStatusColor[step.status]}`} />
                      <span className="text-sm font-bold">{step.title}</span>
                      <Badge variant={step.status === 'completed' ? 'success' : step.status === 'running' ? 'warning' : 'default'}>{step.status}</Badge>
                    </div>
                    <p className="text-xs text-[var(--text3)] mt-1">{step.description}</p>
                    {step.output && (
                      <div className="mt-2 p-3 rounded-lg bg-[var(--surface2)] text-xs font-mono text-green-400">{step.output}</div>
                    )}
                  </div>
                  {step.status === 'pending' && (
                    <button onClick={() => executeStep(idx)} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-xs font-bold flex items-center gap-1">
                      <Play className="w-3 h-3" /> Run
                    </button>
                  )}
                </div>
              </Panel>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-extrabold tracking-tight">Runbook Automation</h1><p className="text-sm text-[var(--text3)] mt-1">Execute operational procedures step-by-step</p></div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {runbooks.map(rb => (
          <Panel key={rb.id}>
            <div className="flex items-start gap-3 mb-3">
              <div className="w-10 h-10 rounded-xl bg-[var(--accent)]/10 flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-[var(--accent2)]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold truncate">{rb.title}</div>
                <div className="text-xs text-[var(--text3)] mt-0.5 line-clamp-2">{rb.description || 'Operational runbook'}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 mb-3">
              {(rb.tags || []).slice(0, 3).map(t => <Badge key={t}>{t}</Badge>)}
            </div>
            <button onClick={() => openRunbook(rb)} className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-bold hover:bg-[var(--accent2)]">
              <Play className="w-3 h-3" /> Execute
            </button>
          </Panel>
        ))}
        {runbooks.length === 0 && (
          <Panel className="col-span-full">
            <div className="text-center py-8 text-sm text-[var(--text3)]">
              No runbooks found. Create runbook entries in the Knowledge Base first.
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}
