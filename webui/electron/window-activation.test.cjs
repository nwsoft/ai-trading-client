"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { activateWindow } = require("./window-activation.cjs");
for (const missing of [null, { isDestroyed: () => true,
  isMinimized: () => { throw new Error("destroyed native window accessed"); } }]) {
  test(`recreates ${missing ? "destroyed" : "missing"} window without accessing native methods`, () => {
    let created = 0;
    assert.equal(activateWindow(missing, () => created++), "created");
    assert.equal(created, 1);
  });
  test(`does not create ${missing ? "destroyed" : "missing"} window before gateway is ready`, () => {
    assert.equal(activateWindow(missing, () => { throw new Error("unexpected create"); }, false), "unavailable");
  });
}
for (const minimized of [false, true]) {
  test(`focuses existing ${minimized ? "minimized" : "visible"} window without creating an engine/window`, () => {
    const calls = [];
    const window = { isDestroyed: () => false, isMinimized: () => minimized,
      restore: () => calls.push("restore"), show: () => calls.push("show"), focus: () => calls.push("focus") };
    assert.equal(activateWindow(window, () => { throw new Error("duplicate window"); }), "focused");
    assert.deepEqual(calls, minimized ? ["restore", "show", "focus"] : ["show", "focus"]);
  });
}
