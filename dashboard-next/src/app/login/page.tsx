'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Activity, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';

function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
    </svg>
  );
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState('');
  const [providers, setProviders] = useState<string[]>([]);
  const { login, loginWithOAuthToken } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  // Load available OAuth providers
  useEffect(() => {
    api.getOAuthProviders().then(d => setProviders(d.providers)).catch(() => {});
  }, []);

  // Handle OAuth callback redirect
  useEffect(() => {
    const oauth = searchParams.get('oauth');
    const token = searchParams.get('token');
    const message = searchParams.get('message');

    if (oauth === 'success' && token) {
      loginWithOAuthToken(token).then(() => {
        router.push('/');
      }).catch(() => {
        setError('OAuth login failed. Please try again.');
      });
    } else if (oauth === 'error') {
      setError(message || 'OAuth login failed. Please try again.');
    }
  }, [searchParams, loginWithOAuthToken, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isSignUp) {
        const res = await api.post('/api/auth/signup', { email, password, name, org_name: orgName });
        if (res.token) {
          await login(email, password);
        }
      } else {
        await login(email, password);
      }
      router.push('/');
    } catch {
      setError(isSignUp ? 'Signup failed. Email may already be registered.' : 'Invalid email or password');
    }
    setLoading(false);
  };

  const handleOAuth = async (provider: string) => {
    setError('');
    setOauthLoading(provider);
    try {
      const url = await api.getOAuthUrl(provider);
      window.location.href = url;
    } catch {
      setError(`Failed to start ${provider} login`);
      setOauthLoading('');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] p-4">
      <div className="w-full max-w-sm animate-slide-up">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[var(--accent)] to-purple-500 flex items-center justify-center mb-4 shadow-lg">
            <Activity className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight">PULSE</h1>
          <p className="text-sm text-[var(--text3)] mt-1">Infrastructure Intelligence Platform</p>
        </div>

        {/* Card */}
        <div className="bg-[var(--surface)] border border-[var(--border-color)] rounded-2xl p-8 space-y-5">
          {/* OAuth buttons */}
          {providers.length > 0 && (
            <>
              <div className="space-y-3">
                {providers.includes('google') && (
                  <button
                    type="button"
                    onClick={() => handleOAuth('google')}
                    disabled={!!oauthLoading}
                    className="w-full flex items-center justify-center gap-3 bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] font-semibold py-3 rounded-lg hover:bg-[var(--surface3)] transition-all disabled:opacity-50"
                  >
                    <GoogleIcon className="w-5 h-5" />
                    {oauthLoading === 'google' ? 'Redirecting...' : 'Continue with Google'}
                  </button>
                )}
                {providers.includes('github') && (
                  <button
                    type="button"
                    onClick={() => handleOAuth('github')}
                    disabled={!!oauthLoading}
                    className="w-full flex items-center justify-center gap-3 bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] font-semibold py-3 rounded-lg hover:bg-[var(--surface3)] transition-all disabled:opacity-50"
                  >
                    <GitHubIcon className="w-5 h-5" />
                    {oauthLoading === 'github' ? 'Redirecting...' : 'Continue with GitHub'}
                  </button>
                )}
              </div>

              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-[var(--border-color)]" />
                <span className="text-[11px] font-bold uppercase tracking-widest text-[var(--text3)]">or</span>
                <div className="flex-1 h-px bg-[var(--border-color)]" />
              </div>
            </>
          )}

          {/* Email/password form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {isSignUp && (
              <>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-3 text-sm outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)] transition-all"
                    placeholder="Your name"
                    required
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Organization</label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={e => setOrgName(e.target.value)}
                    className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-3 text-sm outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)] transition-all"
                    placeholder="Company name"
                    required
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-3 text-sm outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)] transition-all"
                placeholder="you@pulse.dev"
                required
              />
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-widest text-[var(--text3)] mb-2">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full bg-[var(--surface2)] border border-[var(--border-color)] text-[var(--text)] rounded-lg px-4 py-3 pr-12 text-sm outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)] transition-all"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text3)] hover:text-[var(--text)] transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2.5">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[var(--accent)] hover:bg-[var(--accent2)] text-white font-bold py-3 rounded-lg transition-all disabled:opacity-50"
            >
              {loading ? (isSignUp ? 'Creating account...' : 'Signing in...') : (isSignUp ? 'Create Account' : 'Sign In')}
            </button>
          </form>

          <div className="text-center pt-2">
            <button
              type="button"
              onClick={() => { setIsSignUp(!isSignUp); setError(''); }}
              className="text-sm text-[var(--accent)] hover:underline"
            >
              {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
