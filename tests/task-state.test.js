import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_TASK_LENGTH,
  createTask,
  deleteTask,
  isValidTask,
  normalizeTasks,
  setTaskStatus,
  summarizeTasks
} from "../src/task-state.js";

const fixedDate = new Date("2026-10-03T12:00:00.000Z");

test("createTask trims text and creates a pending task", () => {
  const task = createTask("  Plan my day  ", fixedDate, "task-1");
  assert.equal(task.id, "task-1");
  assert.equal(task.title, "Plan my day");
  assert.equal(task.status, "pending");
  assert.equal(task.createdAt, fixedDate.toISOString());
  assert.equal(task.updatedAt, fixedDate.toISOString());
});

test("createTask rejects empty and whitespace-only titles", () => {
  assert.throws(() => createTask(""), /Write a task/);
  assert.throws(() => createTask("   "), /Write a task/);
});

test("createTask rejects oversized titles", () => {
  assert.throws(() => createTask("x".repeat(MAX_TASK_LENGTH + 1)), /1200 characters/);
});

test("createTask rejects non-string input", () => {
  assert.throws(() => createTask(null), /must be a string/);
});

test("setTaskStatus updates only the matching task immutably", () => {
  const first = createTask("First", fixedDate, "first");
  const second = createTask("Second", fixedDate, "second");
  const next = setTaskStatus([first, second], "first", "completed", new Date("2026-10-03T13:00:00.000Z"));
  assert.equal(next[0].status, "completed");
  assert.equal(next[0].updatedAt, "2026-10-03T13:00:00.000Z");
  assert.equal(next[1], second);
  assert.equal(first.status, "pending");
});

test("setTaskStatus rejects unsupported statuses", () => {
  assert.throws(() => setTaskStatus([], "missing", "running"), /Unsupported task status/);
});

test("deleteTask removes only the requested task", () => {
  const tasks = [createTask("First", fixedDate, "first"), createTask("Second", fixedDate, "second")];
  assert.deepEqual(deleteTask(tasks, "first").map(task => task.id), ["second"]);
  assert.equal(tasks.length, 2);
});

test("summarizeTasks reports totals without pretending tasks are running", () => {
  const tasks = [createTask("First", fixedDate, "first"), createTask("Second", fixedDate, "second")];
  const done = setTaskStatus(tasks, "first", "completed", fixedDate);
  assert.deepEqual(summarizeTasks(done), { total: 2, pending: 1, completed: 1, running: 0, approvals: 0 });
});

test("normalizeTasks drops malformed values and caps stored task count", () => {
  const good = createTask("Keep me", fixedDate, "valid");
  const malformed = { id: "bad", title: "Bad", status: "running", createdAt: fixedDate.toISOString() };
  assert.deepEqual(normalizeTasks([good, malformed, null]).map(task => task.id), ["valid"]);
  assert.equal(normalizeTasks(Array.from({ length: 505 }, (_, i) => createTask(`Task ${i}`, fixedDate, String(i)))).length, 500);
});

test("isValidTask rejects invalid timestamps", () => {
  assert.equal(isValidTask({ id: "x", title: "Task", status: "pending", createdAt: "not-a-date" }), false);
});
