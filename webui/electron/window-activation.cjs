"use strict";

// Electron can keep the macOS process alive after its last window is destroyed.
// Never send window methods to that stale native object on a second launch.
function activateWindow(window, createWindow, allowCreate = true) {
  if (!window || window.isDestroyed()) {
    if (allowCreate) { createWindow(); return "created"; }
    return "unavailable";
  }
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
  return "focused";
}
module.exports = { activateWindow };
