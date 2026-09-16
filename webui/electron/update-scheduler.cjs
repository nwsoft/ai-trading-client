function normalizeUpdatePreferences(options = {}) {
  return {
    autoDownload: options.autoDownload === true,
    autoInstallOnAppQuit: options.autoInstallOnAppQuit === true,
  };
}

function shouldInstallUpdateOnQuit({ updateState, autoInstallOnAppQuit, installRequested } = {}) {
  return updateState === "ready" && autoInstallOnAppQuit === true && installRequested !== true;
}

// One main-process timer per application, never one per Settings component.
function createUpdateScheduler({ check, onSchedule = () => {}, now = Date.now,
  setTimer = setTimeout, clearTimer = clearTimeout, initialDelayMs = 15000 }) {
  let enabled = false, intervalMs = 6 * 3600000, timer = null;
  let lastCheckAt = null, nextCheckAt = null, inFlight = null;
  const snapshot = () => ({ autoCheckEnabled: enabled, checkIntervalHours: intervalMs / 3600000, lastCheckAt, nextCheckAt });
  function schedule() {
    if (timer !== null) clearTimer(timer);
    timer = null;
    nextCheckAt = enabled && !inFlight ? Math.max(now() + 1000, lastCheckAt === null ? now() + initialDelayMs : lastCheckAt + intervalMs) : null;
    if (nextCheckAt !== null) timer = setTimer(() => { timer = null; void run().catch(() => {}); }, nextCheckAt - now());
    onSchedule(snapshot());
  }
  function run() {
    if (inFlight) return inFlight;
    lastCheckAt = now();
    // Promise boundary also coalesces two IPC requests in the same event loop.
    inFlight = Promise.resolve().then(check).finally(() => { inFlight = null; schedule(); });
    schedule();
    return inFlight;
  }
  return {
    check: run, snapshot,
    configure(options = {}) {
      const hours = Number(options.intervalHours);
      const nextInterval = Math.min(72, Math.max(1, Number.isFinite(hours) ? hours : 6)) * 3600000;
      const nextEnabled = options.enabled === true;
      if (enabled !== nextEnabled || intervalMs !== nextInterval) {
        enabled = nextEnabled; intervalMs = nextInterval; schedule();
      }
      return snapshot();
    },
    stop() { enabled = false; schedule(); },
  };
}
module.exports = { createUpdateScheduler, normalizeUpdatePreferences, shouldInstallUpdateOnQuit };
