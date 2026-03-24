'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity, Server, BarChart3, Bell, ShieldAlert, AlertTriangle,
  Rss, Network, ScrollText, Globe, Search, TrendingUp,
  MessageSquare, FileText, BookOpen, LayoutDashboard, FolderKanban,
  Workflow, Phone, Radio, ListChecks, Swords, Users, CreditCard,
  ClipboardList, Layers, Settings, Zap, Gauge
} from 'lucide-react';

const navSections = [
  {
    label: 'Monitor',
    items: [
      { href: '/overview', icon: Activity, label: 'Overview' },
      { href: '/nodes', icon: Server, label: 'Nodes' },
      { href: '/metrics', icon: BarChart3, label: 'Metric History' },
    ],
  },
  {
    label: 'Respond',
    items: [
      { href: '/alerts', icon: Bell, label: 'Alerts' },
      { href: '/rules', icon: ShieldAlert, label: 'Alert Rules' },
      { href: '/incidents', icon: AlertTriangle, label: 'Incidents' },
      { href: '/log-alerts', icon: ScrollText, label: 'Log Alerts' },
    ],
  },
  {
    label: 'Observe',
    items: [
      { href: '/events', icon: Rss, label: 'Event Feed' },
      { href: '/topology', icon: Network, label: 'Service Topology' },
      { href: '/logs', icon: ScrollText, label: 'Log Stream' },
      { href: '/synthetic', icon: Globe, label: 'Synthetic Monitoring' },
      { href: '/apm', icon: Zap, label: 'APM / Traces' },
    ],
  },
  {
    label: 'Explore',
    items: [
      { href: '/explorer', icon: Search, label: 'Metric Explorer' },
    ],
  },
  {
    label: 'Reliability',
    items: [
      { href: '/slos', icon: Gauge, label: 'SLO / SLA' },
      { href: '/predictions', icon: TrendingUp, label: 'Predictions' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/ask', icon: MessageSquare, label: 'Ask PULSE' },
      { href: '/reports', icon: FileText, label: 'Reports' },
      { href: '/kb', icon: BookOpen, label: 'Knowledge Base' },
    ],
  },
  {
    label: 'Operate',
    items: [
      { href: '/dashboards', icon: LayoutDashboard, label: 'Dashboards' },
      { href: '/catalog', icon: FolderKanban, label: 'Service Catalog' },
      { href: '/workflows', icon: Workflow, label: 'Workflows' },
      { href: '/oncall', icon: Phone, label: 'On-Call' },
      { href: '/status', icon: Radio, label: 'Status Page' },
      { href: '/templates', icon: ListChecks, label: 'Alert Templates' },
    ],
  },
  {
    label: 'Collaborate',
    items: [
      { href: '/warroom', icon: Swords, label: 'War Room' },
    ],
  },
  {
    label: 'Admin',
    items: [
      { href: '/team', icon: Users, label: 'Users & Teams' },
      { href: '/billing', icon: CreditCard, label: 'Billing' },
      { href: '/audit', icon: ClipboardList, label: 'Audit Log' },
      { href: '/environments', icon: Layers, label: 'Environments' },
      { href: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[220px] bg-[var(--surface)] border-r border-[var(--border-color)] flex flex-col z-40 overflow-y-auto">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-[var(--border-color)]">
        <Link href="/" className="flex items-center gap-2.5 no-underline">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--accent)] to-purple-500 flex items-center justify-center">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <span className="text-[17px] font-extrabold tracking-tight text-[var(--text)]">
            PULSE
          </span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-3 space-y-4 overflow-y-auto">
        {navSections.map(section => (
          <div key={section.label}>
            <div className="text-[10px] font-bold uppercase tracking-[1.2px] text-[var(--text3)] px-2 mb-1.5">
              {section.label}
            </div>
            {section.items.map(item => {
              const isActive = pathname === item.href ||
                (item.href !== '/' && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[13px] font-medium transition-all duration-200 no-underline ${
                    isActive
                      ? 'bg-[var(--accent-soft)] text-[var(--accent2)]'
                      : 'text-[var(--text2)] hover:bg-[var(--surface2)] hover:text-[var(--text)]'
                  }`}
                >
                  <item.icon className="w-4 h-4 flex-shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
