const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const DEFAULT_TIMEOUT_MS = 30_000;

type RequestInterceptor = (path: string, options: RequestInit) => RequestInit;
type ResponseInterceptor = (response: Response) => Response;

/** Decode a JWT payload without verifying signature (client-side only). */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/** Returns true if the token's `exp` claim is in the future. */
export function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== 'number') return true;
  return Date.now() >= payload.exp * 1000;
}

/** Returns seconds until the token expires, or 0 if already expired. */
export function tokenExpiresIn(token: string): number {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== 'number') return 0;
  const remaining = payload.exp * 1000 - Date.now();
  return remaining > 0 ? remaining / 1000 : 0;
}

const MUTATING_METHODS = new Set(['POST', 'PUT', 'DELETE', 'PATCH']);

class ApiClient {
  private token: string | null = null;
  private requestInterceptors: RequestInterceptor[] = [];
  private responseInterceptors: ResponseInterceptor[] = [];
  private maxRetries = 1;
  private retryDelay = 1000;
  private _refreshPromise: Promise<boolean> | null = null;

  constructor() {
    // Default request interceptor: attach timestamps for debugging
    this.addRequestInterceptor((_path, options) => {
      const headers = options.headers as Record<string, string> || {};
      headers['X-Request-Time'] = new Date().toISOString();
      return { ...options, headers };
    });

    // CSRF header on mutating requests
    this.addRequestInterceptor((_path, options) => {
      const method = (options.method || 'GET').toUpperCase();
      if (MUTATING_METHODS.has(method)) {
        const headers = options.headers as Record<string, string> || {};
        headers['X-Requested-With'] = 'XMLHttpRequest';
        return { ...options, headers };
      }
      return options;
    });

    // Default response interceptor: log slow responses
    this.addResponseInterceptor((response) => {
      if (!response.ok && response.status >= 500) {
        console.error(`[API] Server error ${response.status} on ${response.url}`);
      }
      return response;
    });
  }

  addRequestInterceptor(interceptor: RequestInterceptor) {
    this.requestInterceptors.push(interceptor);
  }

  addResponseInterceptor(interceptor: ResponseInterceptor) {
    this.responseInterceptors.push(interceptor);
  }

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

  /** Check whether the current stored token is present and not expired. */
  isTokenValid(): boolean {
    const token = this.getToken();
    if (!token) return false;
    return !isTokenExpired(token);
  }

  /** Get seconds until current token expires (0 if expired or missing). */
  getTokenExpiresIn(): number {
    const token = this.getToken();
    if (!token) return 0;
    return tokenExpiresIn(token);
  }

  /**
   * Try to refresh the current token via /api/auth/refresh.
   * Returns true if the token was refreshed successfully.
   * Deduplicates concurrent refresh calls.
   */
  async refreshToken(): Promise<boolean> {
    if (this._refreshPromise) return this._refreshPromise;

    this._refreshPromise = (async () => {
      try {
        const token = this.getToken();
        if (!token) return false;
        const res = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          },
        });
        if (!res.ok) return false;
        const data = await res.json();
        if (data.token) {
          this.setToken(data.token);
          return true;
        }
        return false;
      } catch {
        return false;
      } finally {
        this._refreshPromise = null;
      }
    })();

    return this._refreshPromise;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
    requestOptions?: { timeout?: number },
  ): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      ...options.headers as Record<string, string>,
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (options.body && typeof options.body === 'string') {
      headers['Content-Type'] = 'application/json';
    }

    let finalOptions: RequestInit = { ...options, headers };

    // Apply request interceptors
    for (const interceptor of this.requestInterceptors) {
      finalOptions = interceptor(path, finalOptions);
    }

    // Request timeout via AbortController
    const timeoutMs = requestOptions?.timeout ?? DEFAULT_TIMEOUT_MS;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    finalOptions.signal = controller.signal;

    let lastError: Error | null = null;

    try {
      for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
        try {
          if (attempt > 0) {
            await new Promise(resolve => setTimeout(resolve, this.retryDelay));
          }

          let res = await fetch(`${API_BASE}${path}`, finalOptions);

          // Apply response interceptors
          for (const interceptor of this.responseInterceptors) {
            res = interceptor(res);
          }

          if (res.status === 401) {
            // Try to refresh token once before giving up
            const refreshed = await this.refreshToken();
            if (refreshed) {
              // Retry the original request with the new token
              const retryHeaders = {
                ...finalOptions.headers as Record<string, string>,
                'Authorization': `Bearer ${this.getToken()}`,
              };
              const retryController = new AbortController();
              const retryTimeoutId = setTimeout(() => retryController.abort(), timeoutMs);
              try {
                const retryRes = await fetch(`${API_BASE}${path}`, {
                  ...finalOptions,
                  headers: retryHeaders,
                  signal: retryController.signal,
                });
                clearTimeout(retryTimeoutId);
                if (retryRes.ok) return retryRes.json();
              } catch {
                clearTimeout(retryTimeoutId);
              }
            }
            // Refresh failed or retry still 401 — redirect to login
            this.setToken(null);
            this.clearAllStorage();
            if (typeof window !== 'undefined') {
              window.location.href = '/login?reason=session_expired';
            }
            throw new ApiError('Unauthorized', 401, 'AUTH_UNAUTHORIZED');
          }

          if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            const message = err.detail || res.statusText;
            // Retry on server errors (5xx) and network-related issues
            if (res.status >= 500 && attempt < this.maxRetries) {
              lastError = new ApiError(message, res.status, 'SERVER_ERROR');
              continue;
            }
            throw new ApiError(message, res.status, err.code || 'REQUEST_FAILED');
          }

          return res.json();
        } catch (err) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            throw new ApiError('Request timed out', 0, 'TIMEOUT');
          }
          if (err instanceof ApiError) {
            // Don't retry client errors (4xx) except on explicit server errors already handled
            if (err.statusCode && err.statusCode < 500) throw err;
            lastError = err;
          } else if (err instanceof TypeError && attempt < this.maxRetries) {
            // Network errors (fetch throws TypeError for network failures)
            lastError = new ApiError(
              'Network error -- check your connection',
              0,
              'NETWORK_ERROR'
            );
            continue;
          } else {
            throw err;
          }
        }
      }
    } finally {
      clearTimeout(timeoutId);
    }

    throw lastError || new ApiError('Request failed after retries', 0, 'RETRY_EXHAUSTED');
  }

  get<T>(path: string, opts?: { timeout?: number }) {
    return this.request<T>(path, {}, opts);
  }

  post<T>(path: string, body?: unknown, opts?: { timeout?: number }) {
    return this.request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }, opts);
  }

  put<T>(path: string, body?: unknown, opts?: { timeout?: number }) {
    return this.request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }, opts);
  }

  patch<T>(path: string, body?: unknown, opts?: { timeout?: number }) {
    return this.request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }, opts);
  }

  delete<T>(path: string, opts?: { timeout?: number }) {
    return this.request<T>(path, { method: 'DELETE' }, opts);
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

  /** Clear all pulse-related keys from localStorage. */
  clearAllStorage() {
    if (typeof window === 'undefined') return;
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('pulse_')) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(k => localStorage.removeItem(k));
  }

  logout() {
    this.setToken(null);
    this.clearAllStorage();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  }

  // OAuth
  async getOAuthProviders() {
    return this.get<OAuthProviders>('/api/auth/oauth/providers');
  }

  async getOAuthUrl(provider: string) {
    const data = await this.get<{ url: string }>(`/api/auth/oauth/${provider}`);
    return data.url;
  }

  /** Exchange an OAuth code for a token via the backend (not URL param). */
  async exchangeOAuthCode(provider: string, code: string) {
    const data = await this.post<{ token: string; user: User }>(
      `/api/auth/oauth/${provider}/callback`,
      { code },
    );
    this.setToken(data.token);
    return data;
  }

  handleOAuthCallback(token: string) {
    this.setToken(token);
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code: string,
  ) {
    super(message);
    this.name = 'ApiError';
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
  oauth_provider?: string;
}

export interface OAuthProviders {
  providers: string[];
}

export const api = new ApiClient();
