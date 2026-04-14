'use client';

import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] p-6">
          <div className="max-w-md w-full text-center space-y-6 animate-fade-in">
            <div className="mx-auto w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-red-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-[var(--text)] mb-2">
                Something went wrong
              </h1>
              <p className="text-sm text-[var(--text3)] leading-relaxed">
                An unexpected error occurred. Please try again or contact support if the problem persists.
              </p>
            </div>
            {this.state.error && (
              <div className="text-left p-3 rounded-xl bg-[var(--surface2)] border border-[var(--border-color)]">
                <p className="text-xs font-mono text-[var(--text3)] break-all">
                  {this.state.error.message}
                </p>
              </div>
            )}
            <button
              onClick={this.handleRetry}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-semibold hover:brightness-110 active:scale-[0.98] transition-all shadow-md"
            >
              <RefreshCw className="w-4 h-4" />
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
