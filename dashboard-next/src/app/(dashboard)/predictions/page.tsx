'use client';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import Badge from '@/components/ui/Badge';
import { TrendingUp, AlertTriangle, Clock } from 'lucide-react';

interface Prediction { id: string; metric: string; node: string; current_value: number; predicted_value: number; threshold: number; eta_hours: number; confidence: number; severity: string; }

export default function PredictionsPage() {
  const { data } = useApi<{ predictions: Prediction[] }>('/api/predictions');
  const predictions = data?.predictions || (Array.isArray(data) ? data as unknown as Prediction[] : []);
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Predictive Forecasts</h1><p className="text-sm text-[var(--text3)] mt-1">AI-powered metric predictions & alerts</p></div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {predictions.map(p => (
          <Panel key={p.id} className={p.eta_hours < 6 ? 'border-red-500/30' : ''}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2"><TrendingUp className="w-4 h-4 text-[var(--accent2)]" /><span className="text-sm font-bold">{p.metric}</span></div>
              <Badge variant={p.severity}>{p.severity}</Badge>
            </div>
            <div className="text-xs text-[var(--text3)] mb-3">{p.node}</div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div className="p-2 rounded-lg bg-[var(--surface2)] text-center"><div className="text-lg font-bold">{p.current_value.toFixed(1)}</div><div className="text-[10px] text-[var(--text3)]">Current</div></div>
              <div className="p-2 rounded-lg bg-[var(--surface2)] text-center"><div className="text-lg font-bold text-orange-400">{p.predicted_value.toFixed(1)}</div><div className="text-[10px] text-[var(--text3)]">Predicted</div></div>
            </div>
            <div className="flex items-center justify-between text-xs text-[var(--text3)]">
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> ETA: {p.eta_hours}h</span>
              <span>Threshold: {p.threshold} · {Math.round(p.confidence * 100)}% conf</span>
            </div>
          </Panel>
        ))}
        {!predictions.length && <div className="col-span-full text-center py-16 text-[var(--text3)]"><TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No predictions</p></div>}
      </div>
    </div>
  );
}
