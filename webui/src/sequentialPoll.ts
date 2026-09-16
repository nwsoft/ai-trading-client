/**
 * Run a network refresh only after the previous attempt has settled.
 * This keeps at most one request per mounted poller when an exchange or DB is slow.
 */
export function startSequentialPoll(
  task: () => Promise<unknown>,
  intervalMs: number,
  { immediate = true }: { immediate?: boolean } = {},
): () => void {
  let active = true;
  let timer: number | undefined;

  const schedule = () => {
    if (!active) return;
    timer = window.setTimeout(() => { void run(); }, Math.max(250, intervalMs));
  };
  const run = async () => {
    if (!active) return;
    try {
      await task();
    } finally {
      schedule();
    }
  };

  if (immediate) void run();
  else schedule();
  return () => {
    active = false;
    if (timer !== undefined) window.clearTimeout(timer);
  };
}
