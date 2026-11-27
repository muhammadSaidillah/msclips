"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

interface PollOptions<T> {
  intervalMs?: number;
  /** Keep polling while this returns true for the latest data. */
  shouldPoll?: (data: T) => boolean;
  /** Restart fetching when these change. */
  deps?: unknown[];
}

/** Fetch now, then re-fetch every `intervalMs` while `shouldPoll(data)` is true. */
export function usePolling<T>(fetcher: () => Promise<T>, options: PollOptions<T> = {}) {
  const { intervalMs = 1500, shouldPoll = () => true, deps = [] } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [settled, setSettled] = useState(false);
  const [kick, setKick] = useState(0);
  const fetcherRef = useRef(fetcher);
  const pollRef = useRef(shouldPoll);
  useLayoutEffect(() => {
    fetcherRef.current = fetcher;
    pollRef.current = shouldPoll;
  });

  const load = useCallback(async (): Promise<T | null> => {
    try {
      const d = await fetcherRef.current();
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError(e as Error);
      return null;
    } finally {
      setSettled(true);
    }
  }, []);

  const depKey = JSON.stringify(deps);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      const d = await load();
      if (!alive) return;
      // On errors keep retrying, but back off.
      if (d === null || pollRef.current(d)) timer = setTimeout(tick, d === null ? intervalMs * 3 : intervalMs);
    };
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [load, intervalMs, depKey, kick]);

  /** Fetch again now and resume polling (e.g. after an action started a new job). */
  const refresh = useCallback(() => setKick((k) => k + 1), []);

  return { data, error, loading: !settled, refresh, setData };
}
