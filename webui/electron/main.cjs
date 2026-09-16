const { app, BrowserWindow, dialog, ipcMain, Menu, net: electronNet, protocol, safeStorage, screen, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const { displayVersion, packageProductVersion, productVersion } = require("./version.cjs");
const { updateErrorMessage } = require("./update-errors.cjs");
const { createUpdateScheduler, normalizeUpdatePreferences, shouldInstallUpdateOnQuit } = require("./update-scheduler.cjs");
let updateScheduler = null;
let updateStatus = { state: "idle" };
function publishUpdateStatus(status) {
  updateStatus = { ...updateStatus, ...status, currentVersion: currentProductVersion() };
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("updater:status", updateStatus);
}

let gatewayProcess = null;
let gatewayBootstrap = null;
let mainWindow = null;
let shutdownPromise = null;
let shutdownComplete = false;
let updaterInstallRequested = false;
let currentWindowMode = "login";
let loginHelpWindow = null;

// Set the product identity before app readiness so the macOS application menu
// and Dock do not retain Electron's development default name.
app.setName("NoahAI");

function currentProductVersion() {
  const candidates = [
    path.resolve(__dirname, "..", "package.json"),
    path.resolve(app.getAppPath(), "package.json"),
  ];
  for (const candidate of candidates) {
    try {
      if (!fs.existsSync(candidate)) continue;
      return packageProductVersion(JSON.parse(fs.readFileSync(candidate, "utf8")), app.getVersion());
    } catch (_) {
      // Try the packaged path or the Electron runtime fallback below.
    }
  }
  return packageProductVersion({}, app.getVersion());
}

function productIconPath() {
  const candidates = [
    path.resolve(__dirname, "..", "build", "icon.png"),
    path.resolve(__dirname, "..", "dist", "icon.png"),
    path.resolve(__dirname, "..", "..", "icon.png"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function savedLoginPath() {
  return path.join(app.getPath("userData"), "saved-login.enc.json");
}

function loadSavedLogin() {
  const filePath = savedLoginPath();
  if (!safeStorage.isEncryptionAvailable() || !fs.existsSync(filePath)) return { saved: false };
  try {
    const payload = JSON.parse(fs.readFileSync(filePath, "utf8"));
    const decrypted = safeStorage.decryptString(Buffer.from(String(payload.ciphertext || ""), "base64"));
    const value = JSON.parse(decrypted);
    if (!value || typeof value.username !== "string" || typeof value.password !== "string") return { saved: false };
    return { saved: true, username: value.username, password: value.password };
  } catch (_) {
    return { saved: false };
  }
}

function saveLoginSecurely(username, password) {
  if (!safeStorage.isEncryptionAvailable()) throw new Error("OS 보안 저장소를 사용할 수 없습니다.");
  const filePath = savedLoginPath();
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const ciphertext = safeStorage.encryptString(JSON.stringify({ username, password })).toString("base64");
  const temporaryPath = `${filePath}.tmp`;
  fs.writeFileSync(temporaryPath, JSON.stringify({ version: 1, ciphertext }), { encoding: "utf8", mode: 0o600 });
  fs.renameSync(temporaryPath, filePath);
  return { saved: true };
}

function clearSavedLogin() {
  const filePath = savedLoginPath();
  if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
  return { saved: false };
}

protocol.registerSchemesAsPrivileged([{ scheme: "noahai", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } }]);

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 3910;
      server.close(() => resolve(port));
    });
  });
}

function pythonExecutable(projectRoot) {
  if (process.env.NOAHAI_PYTHON_EXECUTABLE) return process.env.NOAHAI_PYTHON_EXECUTABLE;
  const candidate = process.platform === "win32"
    ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
    : path.join(projectRoot, ".venv", "bin", "python");
  return fs.existsSync(candidate) ? candidate : (process.platform === "win32" ? "python" : "python3");
}

function terminateOrphanedPackagedEngine() {
  if (process.platform !== "win32" || !app.isPackaged) return;
  // An interrupted updater can leave the previous one-file sidecar alive even
  // though the Electron owner has exited.  That orphan still has the account
  // settings in memory and can rewrite settings.json after the new UI saves.
  // The single-instance lock is already held here, so no healthy NoahAI owner
  // should have a sidecar that belongs to this Windows session.
  spawnSync("taskkill.exe", ["/IM", "NoahAIEngine.exe", "/T", "/F"], {
    windowsHide: true,
    stdio: "ignore",
  });
}

async function startGateway() {
  const externalToken = process.env.NOAHAI_GATEWAY_TOKEN || "";
  const externalUrl = process.env.NOAHAI_GATEWAY_URL || "";
  if (externalUrl && externalToken.length >= 32) return { gatewayUrl: externalUrl, gatewayToken: externalToken };

  const port = await findFreePort();
  const gatewayToken = crypto.randomBytes(36).toString("base64url");
  const gatewayUrl = `http://127.0.0.1:${port}`;
  const projectRoot = path.resolve(__dirname, "..", "..");
  let executable;
  let args;
  let cwd;
  if (app.isPackaged) {
    terminateOrphanedPackagedEngine();
    executable = path.join(process.resourcesPath, "engine", process.platform === "win32" ? "NoahAIEngine.exe" : "noahai-engine");
    args = ["--gateway-only", "--host", "127.0.0.1", "--port", String(port)];
    cwd = path.dirname(executable);
  } else {
    executable = pythonExecutable(projectRoot);
    args = ["-m", "web_platform.launcher", "--host", "127.0.0.1", "--port", String(port)];
    cwd = projectRoot;
  }
  if (app.isPackaged && !fs.existsSync(executable)) throw new Error("패키지에 Python 엔진 sidecar가 없습니다.");
  gatewayProcess = spawn(executable, args, {
    cwd,
    windowsHide: true,
    stdio: ["ignore", "ignore", "pipe"],
    env: {
      ...process.env,
      NOAHAI_GATEWAY_TOKEN: gatewayToken,
      // The engine emits Korean diagnostics and a few status glyphs while it
      // constructs exchange adapters.  Do not inherit a cp949 pipe and report
      // an encoding exception as an exchange API authentication failure.
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
      // The desktop shell owns exactly one local engine process. Runtime
      // construction is still lazy and only happens after an authenticated,
      // explicitly confirmed start command reaches the gateway.
      NOAHAI_ENABLE_WEB_RUNTIME: "1",
    },
  });
  let sidecarError = "";
  gatewayProcess.stderr.on("data", (chunk) => { sidecarError = `${sidecarError}${chunk}`.slice(-4000); });
  gatewayProcess.once("exit", (code) => {
    if (!app.isQuitting && code !== 0 && mainWindow) dialog.showErrorBox("NoahAI 엔진 종료", `로컬 엔진이 예기치 않게 종료되었습니다. (${code ?? "unknown"})`);
  });

  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    if (gatewayProcess.exitCode !== null) throw new Error(`엔진 sidecar 시작 실패: ${sidecarError || gatewayProcess.exitCode}`);
    try {
      const response = await electronNet.fetch(`${gatewayUrl}/api/v1/health`, { cache: "no-store" });
      if (response.ok) return { gatewayUrl, gatewayToken };
    } catch (_) { /* startup polling */ }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`엔진 sidecar 응답 시간 초과: ${sidecarError}`);
}

function stopGatewayAfterHandshake() {
  if (!gatewayProcess) return;
  const pid = gatewayProcess.pid;
  if (process.platform === "win32" && Number.isInteger(pid)) {
    // PyInstaller one-file hosts Uvicorn in a child process. Terminate the
    // owned tree only after the safe-shutdown handshake has completed.
    const result = spawnSync("taskkill.exe", ["/PID", String(pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore",
    });
    if (result.error && !gatewayProcess.killed) gatewayProcess.kill();
  } else if (!gatewayProcess.killed) {
    gatewayProcess.kill();
  }
  gatewayProcess = null;
}

async function requestSafeGatewayShutdown(timeoutMs = 60000) {
  if (shutdownComplete) return { safe_to_exit: true, already_complete: true };
  if (shutdownPromise) return shutdownPromise;
  shutdownPromise = (async () => {
    if (!gatewayBootstrap || !gatewayProcess || gatewayProcess.killed) {
      shutdownComplete = true;
      return { safe_to_exit: true, already_complete: true };
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await electronNet.fetch(`${gatewayBootstrap.gatewayUrl}/api/v1/runtime/shutdown`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${gatewayBootstrap.gatewayToken}`,
          "Content-Type": "application/json",
          "X-NoahAI-Intent": "confirmed",
        },
        body: "{}",
        signal: controller.signal,
        cache: "no-store",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.safe_to_exit !== true) {
        const detailPayload = payload?.detail;
        const runtimeErrors = detailPayload && typeof detailPayload === "object"
          ? detailPayload?.result?.errors
          : null;
        const detail = typeof detailPayload === "string"
          ? detailPayload
          : Array.isArray(runtimeErrors) && runtimeErrors.length
            ? runtimeErrors.join(", ")
            : "거래 워커 또는 기록 저장이 완료되지 않았습니다.";
        throw new Error(detail);
      }
      shutdownComplete = true;
      stopGatewayAfterHandshake();
      return payload;
    } catch (error) {
      if (error && typeof error === "object" && error.name === "AbortError") {
        throw new Error(`안전 종료가 ${Math.round(timeoutMs / 1000)}초 안에 끝나지 않았습니다. 지원 로그에서 종료 지연 worker를 확인하세요.`);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  })();
  try {
    return await shutdownPromise;
  } catch (error) {
    shutdownPromise = null;
    throw error;
  }
}

function completeSafeQuit() {
  app.isQuitting = true;
  if (shouldInstallUpdateOnQuit({
    updateState: updateStatus.state,
    autoInstallOnAppQuit: autoUpdater.autoInstallOnAppQuit,
    installRequested: updaterInstallRequested,
  })) {
    updaterInstallRequested = true;
    publishUpdateStatus({ state: "installing", message: "안전 종료가 완료되어 다운로드한 업데이트를 설치합니다." });
    autoUpdater.quitAndInstall(true, false);
    return { updateInstalling: true };
  }
  app.quit();
  return { updateInstalling: false };
}

function createWindow() {
  if (!gatewayBootstrap) throw new Error("gateway bootstrap is not ready");
  process.env.NOAHAI_GATEWAY_URL = gatewayBootstrap.gatewayUrl;
  process.env.NOAHAI_GATEWAY_TOKEN = gatewayBootstrap.gatewayToken;
  mainWindow = new BrowserWindow({
    // CustomTkinter's geometry("450x680") describes the client area.  Electron
    // normally interprets width/height as the framed window bounds, which made
    // the Web login canvas shorter on macOS/Windows.  Keep the same 450x680
    // drawable area and let each OS add its own title-bar chrome.
    width: 450, height: 680, minWidth: 450, minHeight: 680, useContentSize: true,
    resizable: false, maximizable: false, show: false,
    backgroundColor: "#050a13", title: "NoahAI Finance Decision OS - 로그인",
    ...(productIconPath() ? { icon: productIconPath() } : {}),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => { if (url.startsWith("https://")) shell.openExternal(url); return { action: "deny" }; });
  mainWindow.webContents.on("will-navigate", (event) => event.preventDefault());
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("close", (event) => {
    if (app.isQuitting || shutdownComplete) return;
    event.preventDefault();
    requestSafeGatewayShutdown().then(() => {
      completeSafeQuit();
    }).catch((error) => {
      dialog.showErrorBox("NoahAI 안전 종료 실패", `거래 엔진을 안전하게 정리하지 못해 종료를 중단했습니다.\n\n${error instanceof Error ? error.message : String(error)}`);
    });
  });
  const devUrl = process.env.NOAHAI_WEB_UI_DEV_URL;
  mainWindow.loadURL(devUrl || "noahai://app/index.html");
}

function applyWindowMode(mode) {
  if (!mainWindow || mainWindow.isDestroyed()) return { ok: false };
  const nextMode = mode === "dashboard" ? "dashboard" : "login";
  if (currentWindowMode === nextMode) return { ok: true, mode: nextMode, unchanged: true };
  currentWindowMode = nextMode;
  if (nextMode === "login") updateScheduler?.stop();
  if (nextMode === "dashboard") {
    mainWindow.setResizable(true);
    mainWindow.setMaximizable(true);
    mainWindow.setMinimumSize(1280, 900);
    mainWindow.setSize(1500, 980, true);
    mainWindow.center();
    mainWindow.setTitle(`Noah AI Client - 대시보드 Beta v${currentProductVersion()}`);
    return { ok: true, mode: nextMode };
  }
  mainWindow.unmaximize();
  mainWindow.setResizable(false);
  mainWindow.setMaximizable(false);
  mainWindow.setMinimumSize(450, 680);
  mainWindow.setContentSize(450, 680, true);
  mainWindow.center();
  mainWindow.setTitle("NoahAI Finance Decision OS - 로그인");
  return { ok: true, mode: nextMode };
}

function applyDisplayPreferences(rawPreferences = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) return { ok: false, reason: "window_unavailable" };
  const preset = ["display_standard", "display_large", "display_extra_large"].includes(String(rawPreferences.displayPreset || ""))
    ? String(rawPreferences.displayPreset)
    : "display_standard";
  const profile = {
    display_standard: { width: 1500, height: 980, zoom: 1.0 },
    display_large: { width: 1680, height: 1050, zoom: 1.12 },
    display_extra_large: { width: 1920, height: 1080, zoom: 1.25 },
  }[preset];
  mainWindow.setAlwaysOnTop(Boolean(rawPreferences.alwaysOnTop));
  mainWindow.webContents.setZoomFactor(profile.zoom);
  if (currentWindowMode === "dashboard") {
    const workArea = screen.getDisplayMatching(mainWindow.getBounds()).workAreaSize;
    const minimumWidth = Math.min(1280, workArea.width);
    const minimumHeight = Math.min(900, workArea.height);
    const width = Math.max(minimumWidth, Math.min(profile.width, workArea.width));
    const height = Math.max(minimumHeight, Math.min(profile.height, workArea.height));
    mainWindow.unmaximize();
    mainWindow.setMinimumSize(minimumWidth, minimumHeight);
    mainWindow.setSize(width, height, true);
    mainWindow.center();
  }
  return { ok: true, preset, zoomFactor: profile.zoom };
}

function createLoginHelpWindow() {
  if (loginHelpWindow && !loginHelpWindow.isDestroyed()) {
    loginHelpWindow.focus();
    return { ok: true, reused: true };
  }
  loginHelpWindow = new BrowserWindow({
    width: 640, height: 540, minWidth: 560, minHeight: 460, resizable: true,
    parent: mainWindow || undefined, modal: false, show: false,
    backgroundColor: "#050a13", title: "도움말",
    ...(productIconPath() ? { icon: productIconPath() } : {}),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true,
    },
  });
  loginHelpWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) shell.openExternal(url);
    return { action: "deny" };
  });
  loginHelpWindow.webContents.on("will-navigate", (event) => event.preventDefault());
  loginHelpWindow.once("ready-to-show", () => loginHelpWindow?.show());
  loginHelpWindow.on("closed", () => { loginHelpWindow = null; });
  const devUrl = process.env.NOAHAI_WEB_UI_DEV_URL;
  loginHelpWindow.loadURL(devUrl ? `${devUrl}${devUrl.includes("?") ? "&" : "?"}surface=login-help` : "noahai://app/index.html?surface=login-help");
  return { ok: true, reused: false };
}

function configureUpdater() {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  // Product "Beta" is not the GitHub prerelease channel. With true the
  // provider picks the first Atom entry, which can be an obsolete EXE release.
  // Stable clients must use GitHub /releases/latest, not Atom ordering.
  autoUpdater.allowPrerelease = false;
  autoUpdater.allowDowngrade = false;
  autoUpdater.on("update-available", (info) => publishUpdateStatus({ state: "available", version: displayVersion(info), updaterVersion: info.version }));
  autoUpdater.on("update-not-available", (info) => publishUpdateStatus({ state: "current", version: displayVersion(info) || currentProductVersion(), updaterVersion: info?.version || app.getVersion() }));
  autoUpdater.on("download-progress", (progress) => publishUpdateStatus({ state: "downloading", percent: progress.percent }));
  autoUpdater.on("update-downloaded", (info) => publishUpdateStatus({ state: "ready", version: displayVersion(info), updaterVersion: info.version }));
  autoUpdater.on("error", (error) => publishUpdateStatus({ state: "error", message: updateErrorMessage(error) }));
  updateScheduler = createUpdateScheduler({ onSchedule: publishUpdateStatus, check: async () => {
    if (!app.isPackaged) {
      publishUpdateStatus({ state: "development", message: "GitHub 배포 확인은 설치본에서 제공됩니다." });
      return { development: true, currentVersion: currentProductVersion(), latestVersion: "설치본에서 GitHub 확인" };
    }
    if (["downloading", "ready", "preparing", "installing"].includes(updateStatus.state)) return updateStatus;
    publishUpdateStatus({ state: "checking", message: "" });
    try {
    const result = await autoUpdater.checkForUpdates();
    const latestUpdaterVersion = result?.updateInfo?.version || app.getVersion();
    return {
      development: false,
      currentVersion: currentProductVersion(),
      latestVersion: displayVersion(result?.updateInfo) || productVersion(latestUpdaterVersion),
      updaterVersion: latestUpdaterVersion,
      updateAvailable: Boolean(result?.isUpdateAvailable ?? (result?.updateInfo?.version && result.updateInfo.version !== app.getVersion())),
    };
    } catch (error) {
      const message = updateErrorMessage(error);
      publishUpdateStatus({ state: "error", message });
      throw new Error(message);
    }
  } });
  if (!app.isPackaged) publishUpdateStatus({ state: "development" });
  ipcMain.handle("updater:check", () => updateScheduler.check());
  ipcMain.handle("updater:status", () => updateStatus);
  ipcMain.handle("updater:configure", (_event, options = {}) => {
    const preferences = normalizeUpdatePreferences(options);
    autoUpdater.autoDownload = preferences.autoDownload;
    autoUpdater.autoInstallOnAppQuit = preferences.autoInstallOnAppQuit;
    const configured = {
      ...updateScheduler.configure({ enabled: app.isPackaged && options.enabled === true, intervalHours: options.intervalHours }),
      autoDownloadEnabled: preferences.autoDownload,
      autoInstallOnAppQuitEnabled: preferences.autoInstallOnAppQuit,
    };
    publishUpdateStatus(configured);
    return configured;
  });
  ipcMain.handle("updater:download", async () => {
    try { return await autoUpdater.downloadUpdate(); }
    catch (error) { throw new Error(updateErrorMessage(error)); }
  });
  ipcMain.handle("updater:install", async () => {
    if (updaterInstallRequested) return { state: "preparing" };
    updaterInstallRequested = true;
    publishUpdateStatus({ state: "preparing", message: "거래 워커와 기록을 안전하게 정리하는 중입니다." });
    try {
      await requestSafeGatewayShutdown();
      app.isQuitting = true;
      autoUpdater.quitAndInstall(false, true);
      return { state: "installing" };
    } catch (error) {
      updaterInstallRequested = false;
      const message = error instanceof Error ? error.message : String(error);
      publishUpdateStatus({ state: "error", message: `안전 종료 실패로 업데이트를 중단했습니다: ${message}` });
      throw error;
    }
  });
  ipcMain.handle("window:set-mode", async (_event, mode) => applyWindowMode(String(mode || "login")));
  ipcMain.handle("window:apply-display-preferences", async (_event, preferences) => applyDisplayPreferences(preferences || {}));
  ipcMain.handle("window:open-login-help", async () => createLoginHelpWindow());
  ipcMain.handle("credentials:load", async () => loadSavedLogin());
  ipcMain.handle("credentials:save", async (_event, username, password) => saveLoginSecurely(String(username || ""), String(password || "")));
  ipcMain.handle("credentials:clear", async () => clearSavedLogin());
  ipcMain.handle("window:request-close", async () => {
    if (!mainWindow || mainWindow.isDestroyed()) return { ok: false, reason: "window_unavailable" };
    mainWindow.close();
    return { ok: true, state: "safe_shutdown_requested" };
  });
}

const ownsSingleInstanceLock = app.requestSingleInstanceLock();
if (!ownsSingleInstanceLock) {
  // Do not register ready/startup handlers in the losing process.  Merely
  // calling app.quit() still leaves a window where whenReady can run and spawn
  // a second NoahAIEngine.exe that races the real owner's settings writes.
  app.quit();
} else {
app.on("second-instance", () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } });

app.whenReady().then(async () => {
  // Windows/Linux place Electron's default menu inside the window. NoahAI
  // provides its own product navigation and does not expose developer menus.
  if (process.platform !== "darwin") Menu.setApplicationMenu(null);
  if (process.platform === "darwin" && app.dock && productIconPath()) app.dock.setIcon(productIconPath());
  const distRoot = path.resolve(__dirname, "..", "dist");
  protocol.handle("noahai", (request) => {
    const requestUrl = new URL(request.url);
    const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "") || "index.html";
    const candidate = path.resolve(distRoot, relativePath);
    if (candidate !== distRoot && !candidate.startsWith(`${distRoot}${path.sep}`)) return new Response("Not found", { status: 404 });
    return electronNet.fetch(pathToFileURL(candidate).toString());
  });
  try {
    gatewayBootstrap = await startGateway();
    createWindow();
    configureUpdater();
  } catch (error) {
    dialog.showErrorBox("NoahAI 시작 실패", error instanceof Error ? error.message : String(error));
    app.quit();
  }
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0 && gatewayBootstrap) createWindow(); });
});

app.on("before-quit", (event) => {
  if (shutdownComplete) {
    updateScheduler?.stop();
    app.isQuitting = true;
    stopGatewayAfterHandshake();
    return;
  }
  event.preventDefault();
  if (shutdownPromise) return;
  requestSafeGatewayShutdown().then(() => {
    completeSafeQuit();
  }).catch((error) => {
    dialog.showErrorBox("NoahAI 안전 종료 실패", `종료를 중단했습니다.\n\n${error instanceof Error ? error.message : String(error)}`);
  });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
}
