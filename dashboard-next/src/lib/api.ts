const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:59184';

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) localStorage.setItem('pulse_token', token);
    else localStorage.removeItem('pulse_token');
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('pulse_token');
    }
    return this.token;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      ...options.headers as Record<string, string>,
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (options.body && typeof options.body === 'string') {
      headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (res.status === 401) {
      this.setToken(null);
      if (typeof window !== 'undefined') window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }

    return res.json();
  }

  get<T>(path: string) { return this.request<T>(path); }

  post<T>(path: string, body?: unknown) {
    return this.request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(path: string, body?: unknown) {
    return this.request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(path: string) {
    return this.request<T>(path, { method: 'DELETE' });
  }

  // Auth
  async login(email: string, password: string) {
    const data = await this.post<{ token: string; user: User }>('/api/auth/login', { email, password });
    this.setToken(data.token);
    return data;
  }

  async signup(name: string, email: string, password: string, org_name: string) {
    const data = await this.post<{ token: string; user: User }>('/api/auth/signup', { name, email, password, org_name });
    this.setToken(data.token);
    return data;
  }

  logout() {
    this.setToken(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('pulse_user');
      window.location.href = '/login';
    }
  }
}

export interface User {
  id: number;
  email: string;
  name: string;
  role: string;
  org_name: string;
  avatar_url: string;
  onboarded: boolean;
  settings: Record<string, unknown>;
}

export const api = new ApiClient();
