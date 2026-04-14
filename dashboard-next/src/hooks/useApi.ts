'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api, ApiError } from '@/lib/api';

export interface ApiErrorInfo {
  message: string;
  statusCode?: number;
  code?: string;
}

interface UseApiOptions {
  /** Auto-refetch interval in milliseconds (0 = disabled) */
  refetchInterval?: number;
  /** Keep showing previous data while revalidating */
  staleWhileRevalidate?: boolean;
  /** Skip the initial fetch (useful for conditional fetching) */
  enabled?: boolean;
}

export function useApi<T>(
  path: string,
  deps: unknown[] = [],
  options: UseApiOptions = {},
) {
  const {
    refetchInterval = 0,
    staleWhileRevalidate = true,
    enabled = true,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiErrorInfo | null>(null);
  const [isRevalidating, setIsRevalidating] = useState(false);
  const staleData = useRef<T | null>(null);

  const refetch = useCallback(async (silent = false) => {
    if (!enabled) return;

    // If we have stale data and staleWhileRevalidate is on, do a background refresh
    if (silent && staleWhileRevalidate && staleData.current) {
      setIsRevalidating(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const result = await api.get<T>(path);
      setData(result);
      staleData.current = result;
    } catch (err) {
      const errorInfo: ApiErrorInfo = {
        message: 'Unknown error',
      };
      if (err instanceof ApiError) {
        errorInfo.message = err.message;
        errorInfo.statusCode = err.statusCode;
        errorInfo.code = err.code;
      } else if (err instanceof Error) {
        errorInfo.message = err.message;
      }
      setError(errorInfo);

      // On revalidation failure, keep showing stale data
      if (staleWhileRevalidate && staleData.current) {
        setData(staleData.current);
      }
    }

    setLoading(false);
    setIsRevalidating(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, enabled, staleWhileRevalidate, ...deps]);

  // Initial fetch
  useEffect(() => {
    if (enabled) {
      refetch();
    } else {
      setLoading(false);
    }
  }, [refetch, enabled]);

  // Auto-refetch interval
  useEffect(() => {
    if (!refetchInterval || refetchInterval <= 0 || !enabled) return;

    const id = setInterval(() => {
      refetch(true); // silent revalidation
    }, refetchInterval);

    return () => clearInterval(id);
  }, [refetchInterval, refetch, enabled]);

  return {
    data,
    loading,
    error,
    isRevalidating,
    refetch: () => refetch(false),
  };
}
