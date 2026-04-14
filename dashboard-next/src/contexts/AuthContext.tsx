'use client';

import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, User } from '@/lib/api';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string, org: string) => Promise<void>;
  loginWithOAuthToken: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: async () => {},
  signup: async () => {},
  loginWithOAuthToken: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = api.getToken();
    const stored = localStorage.getItem('pulse_user');
    if (token && stored) {
      try { setUser(JSON.parse(stored)); } catch {}
    }
    setLoading(false);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.login(email, password);
    setUser(data.user);
    localStorage.setItem('pulse_user', JSON.stringify(data.user));
  }, []);

  const signup = useCallback(async (name: string, email: string, password: string, org: string) => {
    const data = await api.signup(name, email, password, org);
    setUser(data.user);
    localStorage.setItem('pulse_user', JSON.stringify(data.user));
  }, []);

  const loginWithOAuthToken = useCallback(async (token: string) => {
    api.handleOAuthCallback(token);
    const user = await api.get<User>('/api/auth/me');
    setUser(user);
    localStorage.setItem('pulse_user', JSON.stringify(user));
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    api.logout();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, loginWithOAuthToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
