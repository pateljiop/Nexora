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
