'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './api';

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch-on-deps with three guarantees the demo depends on:
 * stale responses never overwrite fresh ones, an error keeps the previous data
 * on screen instead of blanking the panel, and every consumer gets a retry.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    fn()
      .then((result) => {
        if (generation.current !== current) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (generation.current !== current) return;
        setError(
          err instanceof ApiError
            ? `${err.path}: ${err.message}${err.status ? ` (${err.status})` : ''}`
            : err instanceof Error
              ? err.message
              : 'Unknown error',
        );
      })
      .finally(() => {
        if (generation.current === current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
