'use client';

import { useEffect, useState } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import { BarChart3, Clock } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface MetricPoint { timestamp: string; cpu_percent: number; memory_percent: number; disk_percent: number; }

export default function MetricsPage() {
  const { data, loading } = useApi<{ system: MetricPoint[] }>('/api/metrics/system');
  const metrics = data?.system || (Array.isArray(data) ? data as unknown as MetricPoint[] : []);

  const chartData = metrics.map(m => ({
    time: new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    CPU: m.cpu_percent,
    Memory: m.memory_percent,
    Disk: m.disk_percent,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">Metric History</h1>
        <p className="text-sm text-[var(--text3)] mt-1">System metrics over time</p>
      </div>
      <Panel title="CPU / Memory / Disk">
        {loading ? (
          <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" /></div>
        ) : chartData.length === 0 ? (
          <div className="text-center py-16 text-[var(--text3)]"><BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" /><p className="text-sm">No metric data yet</p></div>
        ) : (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="time" tick={{ fill: 'var(--text3)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text3)', fontSize: 11 }} domain={[0, 100]} />
                <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border-color)', borderRadius: 12, fontSize: 12 }} />
                <Line type="monotone" dataKey="CPU" stroke="#6366f1" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Memory" stroke="#34d399" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Disk" stroke="#22d3ee" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  );
}
