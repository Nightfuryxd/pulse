'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity, Server, BarChart3, Bell, ShieldAlert, AlertTriangle,
  Rss, Network, ScrollText, Globe, Search, TrendingUp,
  MessageSquare, FileText, BookOpen, LayoutDashboard, FolderKanban,
  Workflow, Phone, Radio, ListChecks, Swords, Users, CreditCard,
  ClipboardList, Layers, Settings, Zap, Gauge, Play, DollarSign, BellRing, X,
  ChevronDown
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
      { href: '/runbooks', icon: Play, label: 'Runbook Automation' },
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
      { href: '/costs', icon: DollarSign, label: 'Cost Monitor' },
      { href: '/notifications', icon: BellRing, label: 'Notifications' },
      { href: '/audit', icon: ClipboardList, label: 'Audit Log' },
      { href: '/environments', icon: Layers, label: 'Environments' },
      { href: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

export default function Sidebar({ mobileOpen, onClose }: { mobileOpen?: boolean; onClose?: () => void }) {
  const pathname = usePathname();
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

  const toggleSection = (label: string) => {
    setCollapsedSections(prev => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  return (
    <>
    {/* Mobile overlay backdrop */}
    {mobileOpen && (
      <div
        className="fixed inset-0 bg-black/50 z-40 lg:hidden"
        onClick={onClose}
      />
    )}
    <aside
      className={`
        fixed left-0 top-0 bottom-0 w-[220px] bg-[var(--surface)]/95 backdrop-blur-md
        border-r border-[var(--border-color)] flex flex-col z-50 overflow-y-auto
        transition-all duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        ${mobileOpen ? 'translate-x-0 opacity-100' : '-translate-x-full opacity-0'}
        lg:translate-x-0 lg:opacity-100
      `}
    >
      {/* Logo */}
      <div className="px-5 py-5 border-b border-[var(--border-color)] flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 no-underline group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--accent)] to-purple-500 flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow duration-200">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <span className="text-[17px] font-extrabold tracking-tight text-[var(--text)]">
            PULSE
          </span>
        </Link>
        <button onClick={onClose} className="lg:hidden p-1.5 rounded-lg hover:bg-[var(--surface2)] transition-colors duration-150">
          <X className="w-4 h-4 text-[var(--text3)]" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-3 space-y-1 overflow-y-auto">
        {navSections.map(section => {
          const isCollapsed = collapsedSections.has(section.label);
          const hasActiveItem = section.items.some(item =>
            pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href))
          );

          return (
            <div key={section.label} className="mb-1">
              <button
                onClick={() => toggleSection(section.label)}
                className="w-full flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-[var(--surface2)] transition-colors duration-150 group"
              >
                <span className={`text-[10px] font-bold uppercase tracking-[1.2px] ${
                  hasActiveItem ? 'text-[var(--accent2)]' : 'text-[var(--text3)]'
                } transition-colors duration-150`}>
                  {section.label}
                </span>
                <ChevronDown
                  className={`w-3 h-3 text-[var(--text3)] opacity-0 group-hover:opacity-100 transition-all duration-200 ${
                    isCollapsed ? '-rotate-90' : 'rotate-0'
                  }`}
                />
              </button>

              <div
                className={`overflow-hidden transition-all duration-250 ease-[cubic-bezier(0.4,0,0.2,1)] ${
                  isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[500px] opacity-100'
                }`}
              >
                <div className="py-0.5">
                  {section.items.map(item => {
                    const isActive = pathname === item.href ||
                      (item.href !== '/' && pathname.startsWith(item.href));
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={onClose}
                        className={`
                          relative flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[13px] font-medium
                          no-underline transition-all duration-150
                          ${isActive
                            ? 'bg-[var(--accent-soft)] text-[var(--accent2)]'
                            : 'text-[var(--text2)] hover:bg-[var(--surface2)] hover:text-[var(--text)] hover:translate-x-0.5'
                          }
                        `}
                      >
                        {/* Active indicator bar */}
                        {isActive && (
                          <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full bg-[var(--accent)] transition-all duration-200" />
                        )}
                        <item.icon className={`w-4 h-4 flex-shrink-0 transition-transform duration-150 ${
                          isActive ? '' : 'group-hover:scale-105'
                        }`} />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </nav>
    </aside>
    </>
  );
}
