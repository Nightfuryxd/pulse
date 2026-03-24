'use client';
import { useState, useEffect } from 'react';
import { useApi } from '@/hooks/useApi';
import Panel from '@/components/ui/Panel';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';
import { Settings } from 'lucide-react';

interface Profile { name: string; email: string; role: string; org_name?: string; settings?: Record<string, unknown>; }

const channels = [
  { id: 'slack', name: 'Slack', icon: '#', placeholder: 'Channel or webhook URL' },
  { id: 'email', name: 'Email', icon: '@', placeholder: 'email@company.com' },
  { id: 'teams', name: 'MS Teams', icon: 'T', placeholder: 'Webhook URL' },
  { id: 'pagerduty', name: 'PagerDuty', icon: 'P', placeholder: 'Integration key' },
  { id: 'opsgenie', name: 'OpsGenie', icon: 'O', placeholder: 'API key' },
  { id: 'telegram', name: 'Telegram', icon: '✈', placeholder: 'Chat ID' },
  { id: 'discord', name: 'Discord', icon: 'D', placeholder: 'Webhook URL' },
  { id: 'webhook', name: 'Webhook', icon: '↗', placeholder: 'https://your-webhook.com' },
  { id: 'sms', name: 'SMS', icon: '✉', placeholder: '+1...' },
];

export default function SettingsPage() {
  const { toast } = useToast();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState('');
  const [org, setOrg] = useState('');
  const [thresholds, setThresholds] = useState({ cpu: 80, memory: 85, disk: 90, cpu_critical: 95, memory_critical: 95 });
  const [enabledChannels, setEnabledChannels] = useState<string[]>([]);
  const [channelTargets, setChannelTargets] = useState<Record<string, string>>({});

  useEffect(() => {
    api.get<Profile>('/api/auth/me').then(u => {
      setProfile(u);
      setName(u.name || '');
      setOrg(u.org_name || '');
      const s = (u.settings || {}) as Record<string, unknown>;
      if (s.thresholds) setThresholds(s.thresholds as typeof thresholds);
      if (s.channels) setEnabledChannels(s.channels as string[]);
      if (s.channel_targets) setChannelTargets(s.channel_targets as Record<string, string>);
    }).catch(() => {});
  }, []);

  const saveProfile = async () => {
    await api.put('/api/auth/settings', { name, org_name: org });
    toast('success', 'Profile saved');
  };

  const saveThresholds = async () => {
    await api.put('/api/auth/settings', { settings: { thresholds } });
    toast('success', 'Thresholds saved');
  };

  const saveChannels = async () => {
    await api.put('/api/auth/settings', { settings: { channels: enabledChannels, channel_targets: channelTargets } });
    toast('success', 'Notification channels saved');
  };

  const toggleChannel = (id: string) => {
    setEnabledChannels(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  };

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Settings</h1><p className="text-sm text-[var(--text3)] mt-1">Profile, thresholds & notifications</p></div>

      <Panel title="Profile">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Name</label>
          <input value={name} onChange={e => setName(e.target.value)} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Organization</label>
          <input value={org} onChange={e => setOrg(e.target.value)} className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm outline-none focus:border-[var(--accent)]" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Email</label>
          <input value={profile?.email || ''} disabled className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm opacity-60" /></div>
          <div><label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Role</label>
          <input value={profile?.role || ''} disabled className="w-full bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-4 py-2.5 text-sm opacity-60" /></div>
        </div>
        <button onClick={saveProfile} className="mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Save Profile</button>
      </Panel>

      <Panel title="Alert Thresholds">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {([
            { key: 'cpu', label: 'CPU Warning' },
            { key: 'memory', label: 'Memory Warning' },
            { key: 'disk', label: 'Disk Warning' },
            { key: 'cpu_critical', label: 'CPU Critical' },
            { key: 'memory_critical', label: 'Memory Critical' },
          ] as const).map(t => (
            <div key={t.key}>
              <label className="block text-xs font-bold text-[var(--text2)] mb-2">{t.label}</label>
              <div className="flex items-center gap-3">
                <input type="range" min="50" max="100" value={thresholds[t.key]} onChange={e => setThresholds({ ...thresholds, [t.key]: parseInt(e.target.value) })} className="flex-1 accent-[var(--accent)]" />
                <span className="text-sm font-bold w-10 text-right">{thresholds[t.key]}%</span>
              </div>
            </div>
          ))}
        </div>
        <button onClick={saveThresholds} className="mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Save Thresholds</button>
      </Panel>

      <Panel title="Notification Channels">
        <div className="space-y-2">
          {channels.map(ch => (
            <div key={ch.id} className="flex items-center gap-3 py-2 border-b border-[var(--border-color)]">
              <label className="flex items-center gap-2 cursor-pointer min-w-[140px]">
                <input type="checkbox" checked={enabledChannels.includes(ch.id)} onChange={() => toggleChannel(ch.id)} className="accent-[var(--accent)]" />
                <span className="text-sm w-5 text-center">{ch.icon}</span>
                <span className="text-sm font-semibold">{ch.name}</span>
              </label>
              <input value={channelTargets[ch.id] || ''} onChange={e => setChannelTargets({ ...channelTargets, [ch.id]: e.target.value })} placeholder={ch.placeholder} className="flex-1 bg-[var(--surface2)] border border-[var(--border-color)] rounded-lg px-3 py-1.5 text-xs outline-none focus:border-[var(--accent)]" />
            </div>
          ))}
        </div>
        <button onClick={saveChannels} className="mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-bold">Save Channels</button>
      </Panel>
    </div>
  );
}
