/**
 * Run a network refresh only after the previous attempt has settled.
 * This keeps at most one request per mounted poller when an exchange or DB is slow.
 */
export function startSequentialPoll(
  task: () => Promise<unknown>,
  intervalMs: number,
  { immediate = true, pauseWhenHidden = false, backoff = false }: { immediate?: boolean; pauseWhenHidden?: boolean; backoff?: boolean } = {},
): () => void {
  let active = true;
  let timer: number | undefined;
  let failures = 0;
  let running = false;

  const schedule = () => {
    if (!active) return;
    const delay = backoff && failures ? Math.min(30000, 5000 * 2 ** (Math.min(failures, 4)-1)) : intervalMs;
    timer = window.setTimeout(() => { void run(); }, Math.max(250, delay));
  };
  const run = async () => {
    if (!active || running) return;
    if (pauseWhenHidden && document.hidden) { schedule(); return; }
    running = true;
    try {
      await task();
      failures = 0;
    } catch {
      failures += 1;
    } finally {
      running = false;
      schedule();
    }
  };

  if (immediate) void run();
  else schedule();
  const onVisibility = () => {
    if (!document.hidden && !running && active) {
      if (timer !== undefined) window.clearTimeout(timer);
      void run();
    }
  };
  if (pauseWhenHidden) document.addEventListener('visibilitychange', onVisibility);
  return () => {
    active = false;
    if (pauseWhenHidden) document.removeEventListener('visibilitychange', onVisibility);
    if (timer !== undefined) window.clearTimeout(timer);
  };
}
