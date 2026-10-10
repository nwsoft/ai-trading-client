const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
const baseURL = process.env.QA_BASE_URL || 'http://127.0.0.1:5193';
const output = new URL('../../reports/strategy-simple-ui/', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
try {
  for (const service of ['crypto', 'stock']) {
    for (const profile of ['beginner', 'advanced']) for (const width of [1440, 1080]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${baseURL}/qa/strategy-feedback.html?service=${service}&profile=${profile}`);
      await page.locator('.version-row').first().waitFor();
      const nav = page.getByRole('navigation', { name: '전략 스튜디오 작업 선택' });
      await page.getByRole('heading', { name: '내 전략', exact: true }).waitFor();
      assert.equal(await page.locator('.legacy-strategy-source-card').isVisible(), false);
      assert.equal(await page.getByRole('button', { name: 'AI 멘토 인터뷰', exact: true }).isVisible(), false);
      await page.screenshot({ path: new URL(`${service}-${profile}-${width}-use.png`, output).pathname.replace(/^\/(.:)/, '$1'), fullPage: true });
      await nav.getByRole('button', { name: /내 전략 만들기/ }).click();
      const editor = page.locator('.legacy-strategy-source-card');
      await editor.waitFor({ state: 'visible' });
      const draft = editor.locator('textarea').first();
      const original = await draft.inputValue();
      await draft.fill('검토 중인 내 전략 초안 · 이동 후 유지');
      await nav.getByRole('button', { name: /공유하기/ }).click();
      await page.getByRole('heading', { name: '내 전략 공유하기', exact: true }).waitFor();
      assert.equal(await editor.isVisible(), false);
      assert.equal(await page.getByRole('button', {name:'버전 삭제',exact:true}).count(), 0);
      assert.equal(await page.getByRole('button', {name:'전략 전체 삭제',exact:true}).count(), 0);
      assert.equal(await page.getByRole('button', {name:'모의 운용 이어가기',exact:true}).count(), 0);
      const exportCount = await page.getByRole('button', { name: '패키지 내보내기', exact: true }).count();
      assert.equal(exportCount > 0, profile !== 'beginner');
      if (profile === 'beginner') assert.equal(await page.getByRole('button', {name:'사용 범위 설정',exact:true}).isVisible(), true);
      await page.getByRole('button', { name: '공유·검증 자세히 배우기' }).click();
      await page.getByRole('heading', { name: '학습·고급 안내', exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'AI 멘토 인터뷰', exact: true }).isVisible(), true);
      await page.getByRole('button', { name: '처음 사용 · 5분 따라 만들기', exact: true }).click();
      const dialog = page.getByRole('dialog');
      await dialog.waitFor();
      await dialog.getByRole('button', { name: '5분 따라 만들기 닫기', exact: true }).click();
      await nav.getByRole('button', { name: /내 전략 만들기/ }).click();
      assert.equal(await draft.inputValue(), '검토 중인 내 전략 초안 · 이동 후 유지');
      await draft.fill(original);
      await page.screenshot({ path: new URL(`${service}-${profile}-${width}-create.png`, output).pathname.replace(/^\/(.:)/, '$1'), fullPage: true });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      assert.equal(await page.evaluate(() => window.__qaReplayRequests), undefined);
      assert.equal(await page.evaluate(() => window.__qaRuntimeCommands), undefined);
      assert.deepEqual(errors, []);
      console.log('PASS', service, profile, width, 'navigation, retained draft, learning, tour, share, layout');
      await page.close();
    }
  }
} finally { await browser.close(); }
