import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

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


test("screen observation is opt-in and model analysis requires explicit consent", () => {
  for (const id of [
    "screen-observer",
    "start-screen-share",
    "capture-screen-frame",
    "analyze-screen-frame",
    "screen-analysis-question",
    "screen-analysis-result",
    "screen-analysis-text",
    "stop-screen-share",
    "screen-frame-image",
    "screen-observer-message"
  ]) {
    assert.match(html, new RegExp('\\bid="' + id + '"'));
  }
  assert.match(main, /navigator\.mediaDevices\.getDisplayMedia/);
  assert.match(main, /addEventListener\("click", startScreenShare\)/);
  assert.match(main, /addEventListener\("click", stopScreenShare\)/);
  assert.match(main, /addEventListener\("pagehide"/);
  const stopBody = main.match(/function stopScreenShare\(\) \{([\s\S]*?)\n\}/)?.[1] ?? "";
  assert.match(stopBody, /screen-frame-image/);
  assert.match(stopBody, /removeAttribute\("src"\)/);
  assert.match(stopBody, /screen-frame-result/);
  assert.match(stopBody, /captured frame and analysis preview were cleared/);
  assert.match(stopBody, /screen-analysis-question/);
  assert.match(stopBody, /analysisText\.textContent = ""/);
  assert.doesNotMatch(stopBody, /remains in browser memory/);
  assert.match(html, /sent for analysis only after you click Analyze and confirm/);
  assert.match(main, /api\("\/api\/screen\/analyze"/);
  assert.match(main, /if \(!window\.confirm\(consentMessage\)\)/);
  assert.match(main, /imageDataUrl: capturedFrameDataUrl/);
  assert.match(main, /capturedFrameDataUrl = null/);
});


test("execution refresh failures remain visible and status can be retried", () => {
  assert.match(html, /id="execution-note" aria-live="polite" aria-atomic="true"/);
  assert.match(main, /function setExecutionStatusError\(message\)/);
  assert.match(main, /The saved run was not retried; use Refresh status/);
  assert.match(main, /Could not refresh run status:/);
  assert.match(main, /Could not confirm cancellation:/);
  assert.match(css, /#execution-note\.error/);
});


test("help dialog accurately describes current local and approval boundaries", () => {
  assert.match(html, /stores tasks and execution history locally when its local server is running/);
  assert.match(html, /remote providers receive it only after you confirm each request/);
  assert.match(html, /full-diff review, explicit approval, and backup/);
  assert.match(html, /general mouse\/keyboard control are not enabled/);
  assert.match(html, /Captured frames stay in browser memory and are cleared when sharing stops/);
  assert.doesNotMatch(html, /does not call an AI model or control your laptop yet/);
});


test("first-run model status is visible and setup never asks for a browser-side API key", () => {
  for (const id of [
    "model-status-dot",
    "model-status-state",
    "model-status-summary",
    "model-setup-button",
    "model-setup-dialog",
    "model-setup-status",
    "model-setup-detail",
    "refresh-model-status",
    "close-model-setup",
    "close-model-setup-footer"
  ]) {
    assert.match(html, new RegExp('\\bid="' + id + '"'));
  }
  assert.match(main, /api\("\/api\/model\/status"\)/);
  assert.match(main, /remote requests need per-goal confirmation/i);
  assert.match(html, /Never paste API keys into this page or commit/);
  assert.match(html, /NEXORA_MODEL_BASE_URL/);
  assert.match(html, /NEXORA_ALLOW_REMOTE_MODEL=0/);
  assert.doesNotMatch(html, /<input[^>]+(?:api.?key|password)/i);
});


test("execution report exposes checkpoint progress and forbids automatic resume", () => {
  assert.match(html, /\bid="execution-checkpoint"/);
  assert.match(main, /execution\.recoveryCheckpoint/);
  assert.match(main, /Automatic resume is disabled/);
  assert.match(main, /Next candidate after review/);
  assert.match(main, /Uncertain outcome needs review/);
  assert.match(css, /\.execution-checkpoint/);
});


test("screen analysis API requires consent and does not persist frames", () => {
  assert.match(main, /consent: true/);
  assert.match(main, /remoteConsent: modelStatus\.remote \? true : false/);
  assert.match(main, /screen-analysis-result/);
  assert.match(html, /Observation only/);
  assert.match(html, /remote providers require a separate confirmation/);
});
