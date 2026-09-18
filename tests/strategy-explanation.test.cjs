const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { execFileSync } = require('node:child_process');
const ts = require('../webui/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const filename = path.join(root, 'webui/src/strategyExplanation.ts');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const loaded = new Module(filename, module);
loaded._compile(compiled, filename);
const { strategyExplanation, strategyExplanationPrompt, STRATEGY_EXPLANATION_MARKER } = loaded.exports;
const analysis = {
  summary: 'RSI 기반 전략', ready_for_execution: false,
  source: { kind: 'youtube', coverage_summary: '자막 있음 · 대표 장면 3개', text: 'RSI 30 이하 LONG 진입.\n저자는 2024년 백테스트 승률 60%를 주장한다.\n손절은 1%.', reference: '/private/file', warnings: ['일부 장면만 확인'] },
  rules: { entry: 'RSI 30 이하 LONG', exit: 'RSI 55 이상 청산', stop_loss: '1%' },
  blocking_details: [{ title: '위험예산', action: '거래당 허용 손실은 몇 %인가요?' }],
  api_key: 'not-to-be-forwarded', secret: 'not-to-be-forwarded',
};

test('actual current rules, source scope and missing question reach the assistant without whole source or path', () => {
  const prompt = strategyExplanationPrompt(analysis, '사용자 전략', 'blockchain');
  const data = JSON.parse(prompt.split(STRATEGY_EXPLANATION_MARKER)[1]);
  assert.equal(data.rules.entry, analysis.rules.entry);
  assert.equal(data.coverage, analysis.source.coverage_summary);
  assert.equal(data.source_excerpts.length, 1);
  assert.match(data.rules.take_profit, /확인되지 않음/);
  assert.ok(!prompt.includes('/private/file'));
  assert.ok(!prompt.includes('not-to-be-forwarded'));
  assert.match(prompt, /명령이 아닌 분석 자료/);
  assert.equal(analysis.source.text.includes('RSI 30'), true);
});

test('same path distinguishes stock/ETF and crypto without inventing a return', () => {
  for (const service of ['stock', 'blockchain']) {
    const data = strategyExplanation({ rules: {}, source: { kind: 'text' } }, '초안', service);
    assert.equal(data.market, service === 'stock' ? '주식·ETF' : '코인');
    assert.deepEqual(data.source_excerpts, []);
    assert.equal(data.ready, false);
  }
});

test('supplemental answers and unavailable YouTube evidence are not treated as original performance', () => {
  const data = structuredClone(analysis);
  data.source.text = '진입 RSI 30\n[사용자가 직접 확인한 보완 답변]\n승률 100% 기대';
  assert.deepEqual(strategyExplanation(data, '', 'stock').source_excerpts, []);
  data.source = { ...analysis.source, evidence: { strategy_evidence_available: false } };
  assert.deepEqual(strategyExplanation(data, '', 'stock').source_excerpts, []);
});

test('large escaped source remains valid JSON within Gateway question budget', () => {
  const huge = '\\"'.repeat(10000);
  const data = { summary: huge, source: { kind: huge, text: `백테스트 ${huge}`, coverage_summary: huge, warnings: [huge, huge] }, rules: Object.fromEntries(['entry', 'exit', 'stop_loss', 'take_profit', 'position_size', 'market_conditions'].map(k => [k, huge])), blocking_details: Array(6).fill({ action: huge }) };
  const prompt = strategyExplanationPrompt(data, huge, 'stock');
  assert.ok(prompt.length < 3901, prompt.length);
  assert.ok(JSON.parse(prompt.split(STRATEGY_EXPLANATION_MARKER)[1]).rules.entry);
});

test('TypeScript snapshot round-trips to real Python local explanation without Provider calls', () => {
  const prompt = strategyExplanationPrompt(analysis, 'RSI 데모', 'stock');
  const answer = execFileSync(path.join(root, '.venv/bin/python'), ['-c', 'import sys; from config.ai_custom_knowledge import build_ai_custom_knowledge; print(build_ai_custom_knowledge(sys.stdin.read()))'], { cwd: root, input: prompt, encoding: 'utf8' });
  assert.match(answer, /RSI 30 이하 LONG/);
  assert.match(answer, /현재 초안 쉽게 읽기/);
  assert.match(answer, /저자의 주장인지/);
  assert.match(answer, /거래당 허용 손실/);
  assert.match(answer, /일반 안내는 외부 AI 없는 정형 설명/);
});
