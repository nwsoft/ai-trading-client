// Run a Vite dev server on 127.0.0.1:4175, then this isolated fixture suite.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || "playwright");
const assert = require("node:assert/strict");

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
  const page = await browser.newPage({ viewport: { width: 1390, height: 970 } });
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  page.on("dialog", dialog => dialog.accept());
  const open = async view => page.goto(`http://127.0.0.1:4175/qa/feedback.html?view=${view}`);
  try {
    await open("stats");
    await page.getByText("12.50 USDT", { exact: true }).first().waitFor();
    assert.equal(await page.getByText("대조 전", { exact: true }).count(), 0);
    await page.getByRole("button", { name: "LIVE", exact: true }).click();
    await page.getByText("대조 전", { exact: true }).first().waitFor();
    await open("analyst");
    await page.getByText("+12.5 USDT", { exact: true }).first().waitFor();
    await page.getByLabel("애널리스트 성과 모드").selectOption("live");
    await page.getByText("대조 전", { exact: true }).first().waitFor();
    await open("market");
    const input = page.getByLabel("조회 종목 (수정 시 직접 입력)");
    assert((await input.inputValue()).includes("^KS11"));
    await input.fill("AAPL,MSFT");
    assert.equal(await page.getByLabel("시장 프리셋").inputValue(), "직접 입력");
    await page.getByRole("button", { name: "시장 현황 조회", exact: true }).click();
    await page.waitForFunction(() => window.feedbackEvents.some(e => e.action === "market"));
    assert.deepEqual(await page.evaluate(() => window.feedbackEvents.find(e => e.action === "market").payload.universe.map(x => x.symbol)), ["AAPL", "MSFT"]);
    await page.getByRole("button", { name: "이벤트·속보", exact: true }).click();
    await page.getByRole("button", { name: "일정·속보 확인", exact: true }).click();
    await page.getByText("데이터 연결·수집 필요", { exact: true }).waitFor();
    assert.equal(await page.getByText("완료", { exact: true }).count(), 0);
    await open("assistant");
    await page.getByRole("button", { name: "심층분석", exact: true }).click();
    await page.getByRole("checkbox").click();
    await page.getByText(/별도 OpenAI Project 키가 저장되지 않았습니다/).waitFor();
    await page.evaluate(() => window.enablePublicProject());
    await page.getByRole("checkbox").check();
    assert(await page.getByRole("checkbox").isChecked());
    await open("learning");
    await page.getByText(/fixture.db · ai_decisions · kis/).waitFor();
    await page.getByRole("combobox").selectOption("kiwoom");
    await page.getByText(/fixture.db · ai_decisions · kiwoom/).waitFor();
    assert.equal(await page.getByText("AI READY", { exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log("PASS: PAPER/LIVE statistics, analyst, market inputs, provider readiness, refreshed Project selection, broker learning UI");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
