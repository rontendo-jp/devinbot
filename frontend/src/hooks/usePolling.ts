import { useEffect, useRef } from 'react';

/**
 * Calls `fetcher` immediately whenever `deps` change and then repeatedly every
 * `intervalMs`, skipping ticks while the tab is hidden (and refetching as soon
 * as it becomes visible again). `intervalMs` may change between renders without
 * restarting the cycle. The AbortSignal is aborted on cleanup so stale
 * responses from a previous dependency set are never applied. `isInitial` is
 * true for the first call of each dependency set so callers can show a spinner
 * only then.
 */
export function usePolling(
  fetcher: (signal: AbortSignal, isInitial: boolean) => Promise<void>,
  intervalMs: number,
  deps: React.DependencyList,
) {
  const fetcherRef = useRef(fetcher);
  const intervalRef = useRef(intervalMs);
  useEffect(() => {
    fetcherRef.current = fetcher;
    intervalRef.current = intervalMs;
  });

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = (isInitial: boolean) => {
      if (document.visibilityState !== 'hidden') {
        fetcherRef.current(controller.signal, isInitial).catch(() => {});
      }
      timer = setTimeout(() => tick(false), intervalRef.current);
    };

    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        clearTimeout(timer);
        tick(false);
      }
    };

    tick(true);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
