import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");

test("every static DOM ID used by the desktop controller exists in index.html", () => {
  const htmlIds = new Set([...html.matchAll(/\bid="([A-Za-z0-9_-]+)"/g)].map(match => match[1]));
  const selectors = new Set([...main.matchAll(/\$\("#([A-Za-z0-9_-]+)"\)/g)].map(match => match[1]));
  const missing = [...selectors].filter(id => !htmlIds.has(id));
  assert.deepEqual(missing, [], "src/main.js references missing HTML IDs");
});

test("workspace proposal review has separate apply and rollback controls", () => {
  for (const id of [
    "workspace-change-history",
    "workspace-change-review",
    "workspace-change-diff",
    "apply-workspace-change",
    "rollback-workspace-change",
    "refresh-workspace-changes"
  ]) {
    assert.match(html, new RegExp('\\bid="' + id + '"'));
  }
  assert.match(main, /prepareWorkspaceChange\(step\.arguments\.path, step\.arguments\.content\)/);
  assert.match(main, /window\.confirm\(/);
});


test("screen observation is opt-in, stoppable, and not uploaded by the current UI", () => {
  for (const id of [
    "screen-observer",
    "start-screen-share",
    "capture-screen-frame",
    "stop-screen-share",
    "screen-frame-image",
    "screen-observer-message"
  ]) {
    assert.match(html, new RegExp('\\\\bid="' + id + '"'));
  }
  assert.match(main, /navigator\\.mediaDevices\\.getDisplayMedia/);
  assert.match(main, /addEventListener\\("click", startScreenShare\\)/);
  assert.match(main, /addEventListener\\("click", stopScreenShare\\)/);
  assert.match(main, /addEventListener\\("pagehide"/);
  assert.match(html, /frames are not sent to a model or server/);
  assert.doesNotMatch(main, /imageDataUrl|fetch\\([^)]*screen-frame-image/);
});
