// Packaged macOS shell + real sidecar smoke; never logs in or submits orders.
const { _electron } = require(process.env.NOAHAI_QA_PLAYWRIGHT || "playwright");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");
(async () => {
  const root = path.resolve(__dirname, "..");
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "noahai-packaged-login-"));
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await _electron.launch({
    env,
    executablePath: path.join(root, "deploy/mac-release/mac-arm64/NoahAI.app/Contents/MacOS/NoahAI"),
    args: ["--user-data-dir=" + profile], timeout: 60000,
  });
  try {
    const page = await app.firstWindow();
    await page.locator("input[type=password]").waitFor({ timeout: 30000 });
    const states = await app.evaluate(({ app }) => ({ packaged: app.isPackaged, version: app.getVersion() }));
    assert.equal(states.packaged, true);
    assert.equal(states.version, "3.9.135");
    const result = await page.evaluate(async () => {
      const { gatewayUrl, gatewayToken } = window.noahAI.bootstrap();
      const response = await fetch(gatewayUrl + "/api/v1/platform", { headers: { Authorization: "Bearer " + gatewayToken } });
      return response.json();
    });
    assert.equal(result.release_version, "3.9.1.35");
    await page.screenshot({ path: path.join(root, "reports/v39135-ui/packaged-mac-login.png") });
    console.log("PASS packaged macOS Electron 3.9.135 + real engine 3.9.1.35 login screen (no account/login/order)");
  } finally {
    await app.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
