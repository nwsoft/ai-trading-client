const { app, BrowserWindow, shell } = require("electron");
const path = require("node:path");

function requireBootstrap() {
  const gatewayUrl = process.env.NOAHAI_GATEWAY_URL || "http://127.0.0.1:3910";
  const gatewayToken = process.env.NOAHAI_GATEWAY_TOKEN || "";
  if (gatewayToken.length < 32) {
    throw new Error("NOAHAI_GATEWAY_TOKEN must contain at least 32 characters");
  }
  return { gatewayUrl, gatewayToken };
}

function createWindow() {
  requireBootstrap();
  const window = new BrowserWindow({
    width: 1500,
    height: 960,
    minWidth: 1080,
    minHeight: 720,
    show: false,
    backgroundColor: "#070d18",
    title: "NoahAI Client 3.9.1.0 Web UI Preview",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.once("ready-to-show", () => window.show());

  const devUrl = process.env.NOAHAI_WEB_UI_DEV_URL;
  if (devUrl) {
    window.loadURL(devUrl);
  } else {
    window.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
