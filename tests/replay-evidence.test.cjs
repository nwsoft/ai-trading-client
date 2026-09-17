const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const Module = require('node:module');
const ts = require('../webui/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const source = path.join(root, 'webui/src/replayEvidence.ts');
const compiled = ts.transpileModule(fs.readFileSync(source, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const module_ = new Module(source, module);
module_._compile(compiled, source);
const { readReplayEvidence, replayAction, formatReplayPercent, formatReplayPrice, replayPriceMinMove, replayMarkerText } = module_.exports;
const venvPython = process.platform === 'win32'
  ? path.join(root, '.venv', 'Scripts', 'python.exe')
  : path.join(root, '.venv', 'bin', 'python');
const metrics = JSON.parse(execFileSync(process.env.NOAHAI_QA_PYTHON || venvPython, ['tests/test_v39137_replay_visualization.py'], { cwd: root, env: { ...process.env, PYTHONPATH: root }, encoding: 'utf8' }));

test('actual Python replay is accepted without recomputing returns', () => {
  const evidence = readReplayEvidence(metrics, 'fixture_v1');
  assert.ok(evidence);
  assert.equal(evidence.equity.at(-1).value, metrics.net_pnl_percent);
  assert.equal(evidence.trades.length, metrics.decisions);
});
for (const variant of ['legacy', 'wrong_version', 'wrong_summary', 'wrong_curve', 'bad_index', 'duplicate_time', 'bad_price', 'missing_cost', 'missing_curve']) {
  test(`reject ${variant} without fabricated chart`, () => {
    const m = structuredClone(metrics);
    if (variant === 'legacy') delete m.replay_visualization;
    if (variant === 'wrong_version') m.replay_visualization.binding.version_id = 'other';
    if (variant === 'wrong_summary') m.net_pnl_percent += 10;
    if (variant === 'wrong_curve') m.replay_visualization.equity[1].value += 1;
    if (variant === 'bad_index') m.trades[0].exit_index = 99999;
    if (variant === 'duplicate_time') m.replay_visualization.candles[1].time = m.replay_visualization.candles[0].time;
    if (variant === 'bad_price') m.replay_visualization.candles[0].low = 99999;
    if (variant === 'missing_cost') delete m.trades[0].cost_percent;
    if (variant === 'missing_curve') delete m.equity_curve_percent;
    assert.equal(readReplayEvidence(m, 'fixture_v1'), null);
  });
}
test('SHORT opening SELL and closing BUY are not mislabeled as LONG', () => {
  assert.equal(replayAction('SHORT', true), '▼ SELL · SHORT 진입');
  assert.equal(replayAction('SHORT', false), '▲ BUY · SHORT 청산');
  assert.equal(replayAction('LONG', true), '▲ BUY · LONG 진입');
  assert.equal(replayAction('LONG', false), '▼ SELL · LONG 청산');
});

for (const [value, expected] of [[-0.251572, '-0.2516%'], [2.289688, '+2.2897%'],
  [0, '0.0000%'], [-0.00000001, '0.0000%'], [-0.0001, '-0.0001%'],
  [100.123456, '+100.1235%'], [-100, '-100.0000%'], [NaN, '미기록']]) {
  test(`percentage points are formatted exactly: ${value}`, () => assert.equal(formatReplayPercent(value), expected));
}
for (const [value, expected] of [[72536.7140731224, '72,536.71'], [70000, '70,000'],
  [99999999.12345, '99,999,999.12'], [0.123456789, '0.123457'], [0.000000123456789, '0.000000123457'],
  [1e-14, '1.00000e-14'], [NaN, '미기록']]) {
  test(`readable price without zeroing tiny coins: ${value}`, () => assert.equal(formatReplayPrice(value), expected));
}
test('formatting never mutates replay evidence', () => {
  const before = structuredClone(metrics);
  metrics.trades.forEach(t => { formatReplayPrice(t.entry_price); formatReplayPrice(t.exit_price); formatReplayPercent(t.net_pnl_percent); });
  assert.deepEqual(metrics, before);
  assert.equal(replayPriceMinMove(70000), 0.01);
  assert.equal(replayPriceMinMove(0.000001), 1e-11);
});
test('all arrows remain while names are restricted to the selected trade, even for 9 clustered trades', () => {
  const markers = Array.from({ length: 9 }, (_, i) => [
    { id: String(i), text: `#${i + 1} BUY LONG 진입` }, { id: String(i), text: `#${i + 1} SELL LONG 청산` },
  ]).flat();
  assert.equal(markers.map(m => replayMarkerText(m.id, m.text, null)).filter(Boolean).length, 0);
  for (const selected of [0, 2, 8]) {
    const texts = markers.map(m => replayMarkerText(m.id, m.text, selected)).filter(Boolean);
    assert.equal(texts.length, 2);
    assert.ok(texts.every(text => text.startsWith(`#${selected + 1} `)));
  }
  assert.equal(markers.length, 18);
});
