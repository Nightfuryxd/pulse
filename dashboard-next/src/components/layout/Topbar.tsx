'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { Bell, Sun, Moon, ChevronDown, ChevronRight, LogOut, Menu, Settings, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import Link from 'next/link';

const breadcrumbLabels: Record<string, string> = {
  overview: 'Overview',
  nodes: 'Nodes',
  metrics: 'Metric History',
  alerts: 'Alerts',
  rules: 'Alert Rules',
  incidents: 'Incidents',
  events: 'Event Feed',
  topology: 'Service Topology',
  logs: 'Log Stream',
  settings: 'Settings',
  team: 'Users & Teams',
  billing: 'Billing',
  dashboards: 'Dashboards',
  explorer: 'Metric Explorer',
  ask: 'Ask PULSE',
  reports: 'Reports',
  slos: 'SLO / SLA',
  predictions: 'Predictions',
  apm: 'APM / Traces',
  synthetic: 'Synthetic Monitoring',
  catalog: 'Service Catalog',
  workflows: 'Workflows',
  oncall: 'On-Call',
  status: 'Status Page',
  warroom: 'War Room',
  kb: 'Knowledge Base',
  runbooks: 'Runbook Automation',
  templates: 'Alert Templates',
  costs: 'Cost Monitor',
  notifications: 'Notifications',
  audit: 'Audit Log',
  environments: 'Environments',
  'log-alerts': 'Log Alerts',
};

export default function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const pathname = usePathname();

  // Build breadcrumbs from pathname
  const pathSegments = pathname.split('/').filter(Boolean);
  const breadcrumbs = pathSegments.map((segment, i) => ({
    label: breadcrumbLabels[segment] || segment.charAt(0).toUpperCase() + segment.slice(1),
    href: '/' + pathSegments.slice(0, i + 1).join('/'),
    isLast: i === pathSegments.length - 1,
  }));

  return (
    <header className="fixed top-0 left-0 lg:left-[220px] right-0 h-14 bg-[var(--surface)]/80 backdrop-blur-xl border-b border-[var(--border-color)]/80 flex items-center justify-between px-4 md:px-6 z-30">
      {/* Left -- hamburger + breadcrumbs */}
      <div className="flex items-center gap-3">
        <button onClick={onMenuClick} className="lg:hidden w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text3)] hover:bg-[var(--surface2)] hover:text-[var(--text)]">
          <Menu className="w-5 h-5" />
        </button>

        {/* Environment badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface2)]/80 border border-[var(--border-color)]">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-xs font-semibold text-[var(--text2)]">Production</span>
        </div>

        {/* Breadcrumb */}
        {breadcrumbs.length > 0 && (
          <nav className="hidden md:flex items-center gap-1 text-sm">
            <ChevronRight className="w-3.5 h-3.5 text-[var(--text3)]" />
            {breadcrumbs.map((crumb) => (
              <span key={crumb.href} className="flex items-center gap-1">
                {crumb.isLast ? (
                  <span className="font-medium text-[var(--text)]">{crumb.label}</span>
                ) : (
                  <>
                    <Link href={crumb.href} className="text-[var(--text3)] hover:text-[var(--text2)] no-underline transition-colors duration-150">
                      {crumb.label}
                    </Link>
                    <ChevronRight className="w-3 h-3 text-[var(--text3)]" />
                  </>
                )}
              </span>
            ))}
          </nav>
        )}
      </div>

      {/* Right -- actions */}
      <div className="flex items-center gap-1.5">
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text3)] hover:bg-[var(--surface2)] hover:text-[var(--text)] active:scale-95"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notifications */}
        <button className="w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text3)] hover:bg-[var(--surface2)] hover:text-[var(--text)] active:scale-95 relative">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center leading-none shadow-sm">
            3
          </span>
        </button>

        {/* User menu */}
        <div className="relative ml-1.5">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--surface2)] active:scale-[0.98]"
          >
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[var(--accent)] to-purple-500 flex items-center justify-center text-white text-xs font-bold ring-2 ring-[var(--surface)] shadow-sm">
              {user?.name?.charAt(0) || 'U'}
            </div>
            <span className="text-sm font-medium text-[var(--text2)] hidden sm:block">
              {user?.name || 'User'}
            </span>
            <ChevronDown className={`w-3 h-3 text-[var(--text3)] transition-transform duration-200 ${showUserMenu ? 'rotate-180' : ''}`} />
          </button>

          {showUserMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
              <div className="absolute right-0 top-full mt-2 w-52 bg-[var(--surface)] border border-[var(--border-color)] rounded-xl shadow-lg z-50 py-1 animate-scale-in origin-top-right">
                <div className="px-3 py-2.5 border-b border-[var(--border-color)]">
                  <div className="text-sm font-semibold text-[var(--text)]">{user?.name}</div>
                  <div className="text-xs text-[var(--text3)] mt-0.5">{user?.email}</div>
                </div>
                <div className="py-1">
                  <Link
                    href="/settings"
                    onClick={() => setShowUserMenu(false)}
                    className="flex items-center gap-2.5 px-3 py-2 text-sm text-[var(--text2)] hover:bg-[var(--surface2)] hover:text-[var(--text)] no-underline transition-colors duration-150"
                  >
                    <User className="w-4 h-4" />
                    Profile
                  </Link>
                  <Link
                    href="/settings"
                    onClick={() => setShowUserMenu(false)}
                    className="flex items-center gap-2.5 px-3 py-2 text-sm text-[var(--text2)] hover:bg-[var(--surface2)] hover:text-[var(--text)] no-underline transition-colors duration-150"
                  >
                    <Settings className="w-4 h-4" />
                    Settings
                  </Link>
                </div>
                <div className="border-t border-[var(--border-color)] pt-1">
                  <button
                    onClick={logout}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors duration-150"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
