'use client';

import { useState } from 'react';
import { Bell, Sun, Moon, ChevronDown, LogOut } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';

export default function Topbar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [showUserMenu, setShowUserMenu] = useState(false);

  return (
    <header className="fixed top-0 left-[220px] right-0 h-14 bg-[var(--surface)] border-b border-[var(--border-color)] flex items-center justify-between px-6 z-30">
      {/* Left — page context */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface2)] border border-[var(--border-color)]">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-xs font-semibold text-[var(--text2)]">Production</span>
        </div>
      </div>

      {/* Right — actions */}
      <div className="flex items-center gap-2">
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text3)] hover:bg-[var(--surface2)] hover:text-[var(--text)] transition-all"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notifications */}
        <button className="w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text3)] hover:bg-[var(--surface2)] hover:text-[var(--text)] transition-all relative">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-400" />
        </button>

        {/* User menu */}
        <div className="relative ml-2">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--surface2)] transition-all"
          >
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[var(--accent)] to-purple-500 flex items-center justify-center text-white text-xs font-bold">
              {user?.name?.charAt(0) || 'U'}
            </div>
            <span className="text-sm font-medium text-[var(--text2)] hidden sm:block">
              {user?.name || 'User'}
            </span>
            <ChevronDown className="w-3 h-3 text-[var(--text3)]" />
          </button>

          {showUserMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
              <div className="absolute right-0 top-full mt-2 w-48 bg-[var(--surface)] border border-[var(--border-color)] rounded-xl shadow-lg z-50 py-1 animate-slide-up">
                <div className="px-3 py-2 border-b border-[var(--border-color)]">
                  <div className="text-sm font-semibold text-[var(--text)]">{user?.name}</div>
                  <div className="text-xs text-[var(--text3)]">{user?.email}</div>
                </div>
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-[var(--surface2)] transition-all"
                >
                  <LogOut className="w-4 h-4" />
                  Sign Out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
