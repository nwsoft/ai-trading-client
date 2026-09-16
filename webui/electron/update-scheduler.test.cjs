const test = require('node:test');
const assert = require('node:assert/strict');
const { createUpdateScheduler, normalizeUpdatePreferences, shouldInstallUpdateOnQuit } = require('./update-scheduler.cjs');

function harness(check = async () => {}) {
  let time = 1000000, id = 0;
  const timers = new Map();
  const scheduler = createUpdateScheduler({ check, now: () => time,
    setTimer: (fn, delay) => { timers.set(++id, { fn, at: time + delay }); return id; },
    clearTimer: id => timers.delete(id),
  });
  return { scheduler, timers, advance: async (ms) => {
    time += ms;
    for (const [key, timer] of [...timers]) if (timer.at <= time) { timers.delete(key); timer.fn(); }
    await new Promise(resolve => setImmediate(resolve));
  } };
}

test('checks at startup and saved interval without opening Settings', async () => {
  let count = 0;
  const h = harness(async () => { count++; });
  h.scheduler.configure({ enabled: true, intervalHours: 2 });
  const original = h.scheduler.snapshot().nextCheckAt;
  h.scheduler.configure({ enabled: true, intervalHours: 2 });
  assert.equal(h.scheduler.snapshot().nextCheckAt, original);
  assert.equal(h.timers.size, 1);
  await h.advance(15000);
  assert.equal(count, 1);
  await h.advance(7200000);
  assert.equal(count, 2);
  assert.equal(h.timers.size, 1);
});

test('disabled still permits manual check, errors retry only on interval', async () => {
  let count = 0;
  const h = harness(async () => { count++; throw new Error('offline'); });
  await assert.rejects(h.scheduler.check(), /offline/);
  assert.equal(h.timers.size, 0);
  h.scheduler.configure({ enabled: true, intervalHours: 1 });
  await h.advance(3600000);
  assert.equal(count, 2);
  assert.equal(h.timers.size, 1);
  h.scheduler.stop();
  await h.advance(7200000);
  assert.equal(count, 2);
});

test('concurrent requests coalesce and stopping during a request leaves no timer', async () => {
  let release, count = 0;
  const h = harness(() => { count++; return new Promise(resolve => { release = resolve; }); });
  h.scheduler.configure({ enabled: true, intervalHours: 2 });
  const a = h.scheduler.check(), b = h.scheduler.check();
  assert.equal(a, b);
  await Promise.resolve();
  assert.equal(count, 1);
  h.scheduler.stop();
  release(); await a;
  assert.equal(h.timers.size, 0);
});

test('settings changes and sleep resume do not create catch-up storms', async () => {
  let count = 0;
  const h = harness(async () => { count++; });
  h.scheduler.configure({ enabled: true, intervalHours: 2 });
  await h.advance(15000);
  h.scheduler.configure({ enabled: true, intervalHours: 1 });
  await h.advance(3600000 * 24);
  assert.equal(count, 2);
  assert.equal(h.timers.size, 1);
});

test('normalizes download and quit-install preferences independently', () => {
  assert.deepEqual(normalizeUpdatePreferences({}), {
    autoDownload: false,
    autoInstallOnAppQuit: false,
  });
  assert.deepEqual(normalizeUpdatePreferences({ autoDownload: true, autoInstallOnAppQuit: true }), {
    autoDownload: true,
    autoInstallOnAppQuit: true,
  });
  assert.deepEqual(normalizeUpdatePreferences({ autoDownload: 1, autoInstallOnAppQuit: 'yes' }), {
    autoDownload: false,
    autoInstallOnAppQuit: false,
  });
});

test('installs on quit only when a downloaded update is ready and the user enabled it', () => {
  assert.equal(shouldInstallUpdateOnQuit({ updateState: 'ready', autoInstallOnAppQuit: true, installRequested: false }), true);
  assert.equal(shouldInstallUpdateOnQuit({ updateState: 'available', autoInstallOnAppQuit: true, installRequested: false }), false);
  assert.equal(shouldInstallUpdateOnQuit({ updateState: 'ready', autoInstallOnAppQuit: false, installRequested: false }), false);
  assert.equal(shouldInstallUpdateOnQuit({ updateState: 'ready', autoInstallOnAppQuit: true, installRequested: true }), false);
});
