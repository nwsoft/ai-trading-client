// Real component + real gateway, synthetic ephemeral storage only.
// Start scripts/qa_insurance_gateway.py and Vite (5173). Needs Playwright/Chrome.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    for (const width of [1490, 1080, 640]) {
      const page = await browser.newPage({ viewport: { width, height: 980 } });
      const errors = []; const external = [];
      page.on('pageerror', e => errors.push(String(e)));
      page.on('request', r => { if (!/^http:\/\/127\.0\.0\.1:(5173|4199)\//.test(r.url()) && !r.url().startsWith('data:')) external.push(r.url()); });
      page.on('dialog', d => d.accept());
      await page.addInitScript(() => { window.noahAI = { bootstrap: () => ({ gatewayUrl: 'http://127.0.0.1:4199', gatewayToken: 'synthetic-insurance-browser-qa-token', desktop: false }) }; });
      await page.goto('http://127.0.0.1:5173/qa/insurance.html');
      await page.getByRole('heading', { name: '내 보험 이해·비교', exact: true }).waitFor();
      await page.waitForTimeout(200);
      if (await page.getByRole('button', { name: '보험 저장소 잠그기', exact: true }).isVisible()) await page.getByRole('button', { name: '보험 저장소 잠그기', exact: true }).click();
      await page.getByLabel('보험 자료 전용 비밀번호 · 12자 이상').fill('synthetic-browser-password-only');
      await page.getByRole('button', { name: /암호화 보험 저장소 만들기|보험 저장소 열기/ }).click();
      await page.getByText('2. 계약·보장 입력 및 확인', { exact: true }).click();
      await page.getByLabel('상품·계약 이름', { exact: true }).fill(`합성 보험 ${width}`);
      await page.getByLabel('보험사', { exact: true }).fill('가상 보험사');
      await page.getByLabel('계약 상태', { exact: true }).selectOption('active');
      await page.getByLabel('회차 보험료 · 미확인은 빈칸').fill('840000');
      await page.getByLabel('납입 주기', { exact: true }).selectOption('annual');
      await page.getByRole('button', { name: '보장 항목 추가', exact: true }).click();
      await page.getByLabel('원문 보장명', { exact: true }).fill('합성 상해 정액');
      await page.getByLabel('지급 방식', { exact: true }).selectOption('fixed');
      await page.getByLabel('가입금액 · 지급 확정액 아님', { exact: true }).fill('1000000');
      await page.getByLabel('지급 조건', { exact: true }).fill('테스트 조건 · 보험사 확인 필요');
      await page.getByLabel('보장 제외', { exact: true }).fill('테스트 제외 사항');
      await page.getByLabel('본인 또는 제공 권한이 있는 자료를 입력했습니다.').check();
      await page.getByLabel('원문과 입력값·단위·기간을 대조했습니다. 사용자 확인은 보험사 검증이나 지급 보장이 아닙니다.').check();
      await page.getByRole('button', { name: '확인한 계약 저장', exact: true }).click();
      const card = page.locator('.insurance-policy-list article').filter({ hasText: `합성 보험 ${width}` });
      await card.waitFor();
      assert((await card.innerText()).includes('70000.00 KRW'));
      await card.getByRole('checkbox').check();
      await page.getByRole('button', { name: '선택한 계약 점검', exact: true }).click();
      await page.getByRole('button', { name: '상담 질문지 미리보기', exact: true }).click();
      await page.getByRole('heading', { name: '로컬 보고서 · 전송하지 않음' }).waitFor();
      assert(await page.getByRole('button', { name: '검토한 질문지 TXT 저장' }).isDisabled());
      await page.getByLabel('내용과 민감정보를 직접 검토했습니다. 아래 저장은 암호화되지 않은 TXT입니다.').check();
      const reportDownload = page.waitForEvent('download');
      await page.getByRole('button', { name: '검토한 질문지 TXT 저장' }).click();
      assert.equal((await reportDownload).suggestedFilename(), 'noah-insurance-questions.txt');
      const backupDownload = page.waitForEvent('download');
      await page.getByRole('button', { name: '암호화 백업 저장', exact: true }).click();
      assert.equal((await backupDownload).suggestedFilename(), 'noah-insurance.noahinsurance');
      if (width === 1490) {
        await page.getByText('1. 원문 등록·대조 · PDF / PNG / JPEG', { exact: true }).click();
        await page.getByLabel('본인 또는 제공·처리 권한이 있는 자료입니다. 주민번호·불필요한 건강정보는 사전에 가렸습니다.').check();
        const image = execFileSync('.venv/bin/python', ['-c', 'import io,sys;from PIL import Image;b=io.BytesIO();Image.new("RGB",(40,40),"white").save(b,format="PNG");sys.stdout.buffer.write(b.getvalue())']);
        await page.getByLabel('보험 원문 선택', { exact: true }).setInputFiles({ name: 'synthetic.png', mimeType: 'image/png', buffer: image });
        await page.getByRole('button', { name: '원문 대조', exact: true }).waitFor();
        await page.getByRole('button', { name: '원문 대조', exact: true }).click();
        await page.getByAltText('등록한 보험 원문 · 수동 대조용').waitFor();
        await page.getByRole('button', { name: '이 원문에서 입력 초안 만들기 · 자동 승인 안 함', exact: true }).click();
        await page.getByLabel('상품·계약 이름', { exact: true }).fill('합성 비교 견적');
        await page.getByLabel('자료 구분', { exact: true }).selectOption('quote');
        await page.getByLabel('회차 보험료 · 미확인은 빈칸').fill('60000');
        await page.getByLabel('납입 주기', { exact: true }).selectOption('monthly');
        await page.getByRole('button', { name: '근거 연결 추가', exact: true }).click();
        await page.getByLabel('원문 인용 · 텍스트는 그대로 복사, 이미지는 직접 대조', { exact: true }).fill('합성 이미지 수동 전사');
        await page.getByLabel('본인 또는 제공 권한이 있는 자료를 입력했습니다.').check();
        await page.getByLabel('원문과 입력값·단위·기간을 대조했습니다. 사용자 확인은 보험사 검증이나 지급 보장이 아닙니다.').check();
        await page.getByRole('button', { name: '확인한 계약 저장', exact: true }).click();
        const quote = page.locator('.insurance-policy-list article').filter({ hasText: '합성 비교 견적' });
        await quote.getByRole('checkbox').check();
        await page.getByRole('button', { name: '선택한 두 자료 비교', exact: true }).click();
        await page.getByText(/월 환산 보험료 차이.*-10000.00 KRW/).waitFor();
        await page.getByRole('button', { name: '원문 삭제', exact: true }).click();
        await quote.getByText(/원문 삭제 · 재확인 필요/).waitFor();
        await quote.getByRole('button', { name: '수정·근거 확인', exact: true }).click();
        await page.getByLabel('본인 또는 제공 권한이 있는 자료를 입력했습니다.').check();
        await page.getByRole('button', { name: '확인 전 초안 저장', exact: true }).click();
        await quote.getByText(/확인 전/).waitFor();
        await quote.getByRole('button', { name: '계약 삭제', exact: true }).click();
        await quote.waitFor({ state: 'detached' });
      }
      await page.getByRole('heading', { name: '내 보험 이해·비교', exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/noah-v3922-insurance-${width}.png`, fullPage: false });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      assert.equal(await page.getByRole('alert').count(), 0);
      assert.deepEqual(errors, []); assert.deepEqual(external, []);
      await page.getByRole('button', { name: '보험 저장소 잠그기', exact: true }).click();
      await page.getByLabel('보험 자료 전용 비밀번호 · 12자 이상').waitFor();
      assert.equal(await page.locator('.insurance-policy-list').count(), 0);
      if (width === 640) {
        await page.clock.install();
        await page.getByLabel('보험 자료 전용 비밀번호 · 12자 이상').fill('synthetic-browser-password-only');
        await page.getByRole('button', { name: '보험 저장소 열기', exact: true }).click();
        await page.getByRole('button', { name: '보험 저장소 잠그기', exact: true }).waitFor();
        await page.route('http://127.0.0.1:4199/**', route => route.abort());
        await page.clock.fastForward(900001);
        await page.getByLabel('보험 자료 전용 비밀번호 · 12자 이상').waitFor();
        assert.equal(await page.locator('.insurance-policy-list').count(), 0);
        assert.deepEqual(errors, []);
      }
      await page.close();
    }
    console.log('insurance UI: 3 widths, real encrypted save/comparison/report/backup/lock; no external requests; PASS');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
