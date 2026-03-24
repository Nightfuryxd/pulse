'use client';
import { useState } from 'react';
import { api } from '@/lib/api';
import Panel from '@/components/ui/Panel';
import { MessageSquare, Send, Zap } from 'lucide-react';

interface NlResult { answer: string; query_type: string; data?: unknown; }

export default function AskPage() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<NlResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);

  const ask = async () => {
    if (!question.trim()) return;
    setLoading(true);
    try {
      const r = await api.post<NlResult>('/api/nl/query', { question });
      setResult(r);
      setHistory(prev => [...prev, { q: question, a: r.answer }]);
    } catch { setResult({ answer: 'Unable to process query', query_type: 'error' }); }
    setLoading(false);
    setQuestion('');
  };

  const suggestions = ['What is the current CPU usage?', 'Show me critical alerts', 'Which nodes have high memory?', 'What was the last incident?'];

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Ask PULSE</h1><p className="text-sm text-[var(--text3)] mt-1">Natural language infrastructure queries</p></div>

      <Panel>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <MessageSquare className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--text3)]" />
            <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && ask()}
              placeholder="Ask anything about your infrastructure..." className="w-full pl-12 pr-4 py-3.5 rounded-xl bg-[var(--surface2)] border border-[var(--border-color)] text-sm text-[var(--text)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]" />
          </div>
          <button onClick={ask} disabled={loading} className="px-5 py-3 rounded-xl bg-[var(--accent)] text-white font-bold hover:bg-[var(--accent2)] disabled:opacity-50 flex items-center gap-2">
            <Send className="w-4 h-4" /> Ask
          </button>
        </div>
        {!history.length && <div className="mt-4 flex flex-wrap gap-2">
          {suggestions.map(s => <button key={s} onClick={() => { setQuestion(s); }} className="px-3 py-1.5 rounded-lg bg-[var(--surface2)] text-xs text-[var(--text3)] hover:text-[var(--text)] hover:bg-[var(--surface3)]">{s}</button>)}
        </div>}
      </Panel>

      {history.map((h, i) => (
        <div key={i} className="space-y-3">
          <div className="flex justify-end"><div className="px-4 py-3 rounded-2xl rounded-tr-sm bg-[var(--accent-soft)] text-sm max-w-lg">{h.q}</div></div>
          <div className="flex justify-start"><div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-[var(--surface2)] text-sm max-w-lg flex items-start gap-2">
            <Zap className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" /><span>{h.a}</span>
          </div></div>
        </div>
      ))}

      {loading && <div className="flex justify-start"><div className="px-4 py-3 rounded-2xl bg-[var(--surface2)] text-sm"><div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" /></div></div>}
    </div>
  );
}
