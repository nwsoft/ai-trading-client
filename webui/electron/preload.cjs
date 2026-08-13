const { contextBridge } = require("electron");

const bootstrap = Object.freeze({
  gatewayUrl: process.env.NOAHAI_GATEWAY_URL || "http://127.0.0.1:3910",
  gatewayToken: process.env.NOAHAI_GATEWAY_TOKEN || "",
  desktop: true,
});

contextBridge.exposeInMainWorld("noahAI", {
  bootstrap: () => ({ ...bootstrap }),
});
