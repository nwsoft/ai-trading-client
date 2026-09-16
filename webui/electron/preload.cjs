const { contextBridge, ipcRenderer } = require("electron");

const bootstrap = Object.freeze({
  gatewayUrl: process.env.NOAHAI_GATEWAY_URL || "http://127.0.0.1:3910",
  gatewayToken: process.env.NOAHAI_GATEWAY_TOKEN || "",
  desktop: true,
});

contextBridge.exposeInMainWorld("noahAI", {
  bootstrap: () => ({ ...bootstrap }),
  window: {
    setMode: (mode) => ipcRenderer.invoke("window:set-mode", mode),
    applyDisplayPreferences: (preferences) => ipcRenderer.invoke("window:apply-display-preferences", preferences),
    openLoginHelp: () => ipcRenderer.invoke("window:open-login-help"),
    requestClose: () => ipcRenderer.invoke("window:request-close"),
  },
  credentials: {
    load: () => ipcRenderer.invoke("credentials:load"),
    save: (username, password) => ipcRenderer.invoke("credentials:save", username, password),
    clear: () => ipcRenderer.invoke("credentials:clear"),
  },
  updater: {
    configure: (options) => ipcRenderer.invoke("updater:configure", options),
    getStatus: () => ipcRenderer.invoke("updater:status"),
    check: () => ipcRenderer.invoke("updater:check"),
    download: () => ipcRenderer.invoke("updater:download"),
    install: () => ipcRenderer.invoke("updater:install"),
    onStatus: (listener) => {
      const handler = (_event, status) => listener(status);
      ipcRenderer.on("updater:status", handler);
      return () => ipcRenderer.removeListener("updater:status", handler);
    },
  },
});
