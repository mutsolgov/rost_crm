import { useEffect, useRef, useState } from 'react';
import type { DependencyList } from 'react';
import { makeMutationKey } from './api';

export function useResource<T>(loader: () => Promise<T>, dependencies: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [reloadCount, setReloadCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    loader().then(value => { if (!cancelled) setData(value); })
      .catch(problem => { if (!cancelled) setError(problem); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // Callers specify stable primitive dependencies, like a request key.
  }, [...dependencies, reloadCount]);
  const reload = () => setReloadCount(c => c + 1);
  return { data, error, loading, reload };
}

export function useMutationKey() {
  const attempt = useRef<{ body: string; key: string } | null>(null);
  return {
    forBody(body: unknown) {
      const encoded = JSON.stringify(body);
      if (attempt.current?.body !== encoded) attempt.current = { body: encoded, key: makeMutationKey() };
      return attempt.current.key;
    },
    clear() { attempt.current = null; },
  };
}

export function useDebounced<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useRoute() {
  const [hash, setHash] = useState(window.location.hash || '#/overview');
  useEffect(() => {
    const update = () => setHash(window.location.hash || '#/overview');
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?');
  return { path, query: new URLSearchParams(query), navigate: (target: string) => { window.location.hash = '/' + target; } };
}

