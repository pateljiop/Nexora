import { createTask, deleteTask, normalizeTasks, setTaskStatus, summarizeTasks } from "./task-state.js";

const STORAGE_KEY = "nexora.virtual-hariom.tasks.v1";
const ACTIVITY_KEY = "nexora.virtual-hariom.activity.v1";
const MIGRATION_KEY = "nexora.virtual-hariom.sqlite-migration.v1";
const $ = selector => document.querySelector(selector);
const taskForm = $("#task-form");
const taskInput = $("#task-input");
const taskList = $("#task-list");
const activityList = $("#activity-list");
const toast = $("#toast");
const sidebar = $("#sidebar");
const aboutDialog = $("#about-dialog");
let currentView = "overview";
let backendAvailable = false;
let tasks = readJson(STORAGE_KEY, []);
let activities = readJson(ACTIVITY_KEY, []);

tasks = normalizeTasks(tasks);
activities = normalizeActivities(activities);
$("#year").textContent = String(new Date().getFullYear());

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    showToast("Browser storage is unavailable or full. Your latest change may not persist.");
    return false;
  }
}

function normalizeActivities(value) {
  if (!Array.isArray(value)) return [];
  return value.filter(item => item && typeof item.message === "string" && typeof item.at === "string")
    .slice(0, 30).map(item => ({ message: item.message.slice(0, 180), detail: String(item.detail || "").slice(0, 220), at: item.at }));
}


async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
    cache: "no-store"
  });
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.error || `Local API error (${response.status}).`);
  return payload;
}

function logActivity(message, detail = "") {
  activities.unshift({ message, detail, at: new Date().toISOString() });
  activities = activities.slice(0, 30);
  writeJson(ACTIVITY_KEY, activities);
  renderActivity();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => toast.classList.remove("show"), 3200);
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "RECENTLY";
  const delta = Math.max(0, Date.now() - date.getTime());
  if (delta < 60000) return "JUST NOW";
  if (delta < 3600000) return `${Math.floor(delta / 60000)} MIN AGO`;
  if (delta < 86400000) return `${Math.floor(delta / 3600000)} HR AGO`;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" }).toUpperCase();
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderTasks() {
  taskList.replaceChildren();
  const visibleTasks = currentView === "tasks" ? tasks : tasks.slice(0, 5);
  $("#list-title").textContent = currentView === "tasks" ? "All your tasks" : "Your tasks";
  $("#list-subtitle").textContent = backendAvailable ? "Saved on this laptop in the local SQLite database." : currentView === "tasks" ? "Every task you have saved in this browser." : "Small steps make progress visible.";
  $("#view-all").hidden = currentView === "tasks" || tasks.length <= 5;

  if (!visibleTasks.length) {
    const empty = makeElement("div", "empty-state");
    const icon = makeElement("div", "empty-orbit", "✳");
    const title = makeElement("strong", "", currentView === "tasks" ? "No tasks yet" : "Your workspace starts here");
    const copy = makeElement("p", "", backendAvailable ? "Add a goal above. It will be saved on this laptop." : "Tell Virtual Hariom what you want to work on. Your task will be saved in this browser.");
    empty.append(icon, title, copy);
    taskList.append(empty);
    return;
  }

  for (const task of visibleTasks) {
    const row = makeElement("article", `task-row ${task.status}`);
    const check = makeElement("button", "task-check", task.status === "completed" ? "✓" : "");
    check.type = "button";
    check.setAttribute("aria-label", task.status === "completed" ? "Mark task as pending" : "Mark task as completed");
    check.setAttribute("aria-pressed", String(task.status === "completed"));
    check.addEventListener("click", () => toggleTask(task.id));

    const main = makeElement("div", "task-main");
    main.append(makeElement("p", "task-title", task.title));
    const meta = makeElement("div", "task-meta");
    meta.append(makeElement("span", `task-badge ${task.status}`, task.status), makeElement("span", "", formatTime(task.createdAt)));
    main.append(meta);

    const actions = makeElement("div", "task-actions");
    const remove = makeElement("button", "task-action", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", "Delete task");
    remove.title = "Delete task";
    remove.addEventListener("click", () => removeTask(task.id));
    actions.append(remove);
    row.append(check, main, actions);
    taskList.append(row);
  }
}

function renderActivity() {
  activityList.replaceChildren();
  const items = activities.slice(0, currentView === "activity" ? 30 : 5);
  if (!items.length) {
    const empty = makeElement("div", "empty-state");
    empty.append(makeElement("div", "empty-orbit", "⌁"), makeElement("strong", "", "No activity yet"), makeElement("p", "", "Task creation and updates will appear here."));
    activityList.append(empty);
    return;
  }
  for (const item of items) {
    const entry = makeElement("div", "activity-entry");
    const rail = makeElement("span", "activity-rail");
    const icon = makeElement("span", "activity-icon", "✳");
    const content = makeElement("div");
    content.append(makeElement("strong", "", item.message));
    if (item.detail) content.append(makeElement("p", "", item.detail));
    content.append(makeElement("time", "", formatTime(item.at)));
    entry.append(rail, icon, content);
    activityList.append(entry);
  }
}

function renderStats() {
  const summary = summarizeTasks(tasks);
  $("#task-count").textContent = String(summary.total);
  $("#stat-total").textContent = String(summary.total).padStart(2, "0");
  $("#stat-running").textContent = String(summary.running).padStart(2, "0");
  $("#stat-approval").textContent = String(summary.approvals).padStart(2, "0");
}

function renderNavigation() {
  document.querySelectorAll("[data-view]").forEach(button => {
    const active = button.dataset.view === currentView || (currentView === "overview" && button.dataset.view === "overview");
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("#breadcrumb-current").textContent = currentView === "overview" ? "Home" : currentView === "tasks" ? "My tasks" : "Activity";
  $("#session-label").textContent = currentView === "activity" ? "RECENT EVENTS" : currentView === "tasks" ? "ALL TASKS" : backendAvailable ? "LOCAL SQLITE SESSION" : "BROWSER PREVIEW";
  renderTasks();
  renderActivity();
}

function render() {
  renderStats();
  renderNavigation();
}

async function addTask(title) {
  if (backendAvailable) {
    const result = await api("/api/tasks", { method: "POST", body: JSON.stringify({ title }) });
    tasks = [result.task, ...tasks].slice(0, 500);
    await refreshFromServer();
  } else {
    const task = createTask(title);
    tasks = [task, ...tasks].slice(0, 500);
    writeJson(STORAGE_KEY, tasks);
    logActivity("Task added to your workspace", task.title);
  }
  currentView = "overview";
  render();
  taskInput.value = "";
  taskInput.blur();
  showToast(backendAvailable ? "Saved to this laptop. AI execution is not connected yet." : "Saved in this browser. Local server is not connected.");
}

async function toggleTask(id) {
  const task = tasks.find(item => item.id === id);
  if (!task) return;
  const status = task.status === "completed" ? "pending" : "completed";
  if (backendAvailable) {
    await api(`/api/tasks/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ status }) });
    await refreshFromServer();
  } else {
    tasks = setTaskStatus(tasks, id, status);
    writeJson(STORAGE_KEY, tasks);
    logActivity(status === "completed" ? "Task marked complete" : "Task reopened", task.title);
    render();
  }
}

async function removeTask(id) {
  const task = tasks.find(item => item.id === id);
  if (!task) return;
  if (backendAvailable) {
    await api(`/api/tasks/${encodeURIComponent(id)}`, { method: "DELETE" });
    await refreshFromServer();
  } else {
    tasks = deleteTask(tasks, id);
    writeJson(STORAGE_KEY, tasks);
    logActivity("Task removed", task.title);
    render();
  }
  showToast(backendAvailable ? "Task removed from this laptop." : "Task removed from this browser.");
}

taskForm.addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await addTask(taskInput.value);
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not add that task.");
    taskInput.focus();
  }
});

document.querySelectorAll("[data-view]").forEach(button => {
  button.addEventListener("click", () => {
    currentView = button.dataset.view;
    sidebar.classList.remove("open");
    renderNavigation();
    if (currentView === "activity") $(".activity-surface").scrollIntoView({ behavior: "smooth", block: "start" });
    if (currentView === "tasks") $(".task-surface").scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

document.querySelectorAll("[data-prompt]").forEach(button => {
  button.addEventListener("click", () => {
    taskInput.value = button.dataset.prompt || "";
    taskInput.focus();
    sidebar.classList.remove("open");
    document.querySelector(".command-panel").scrollIntoView({ behavior: "smooth", block: "center" });
  });
});

$("#view-all").addEventListener("click", () => {
  currentView = "tasks";
  renderNavigation();
  $(".task-surface").scrollIntoView({ behavior: "smooth", block: "start" });
});

$("#menu-toggle").addEventListener("click", () => sidebar.classList.toggle("open"));
$("#help-button").addEventListener("click", () => {
  if (typeof aboutDialog.showModal === "function") aboutDialog.showModal();
  else showToast("Nexora is in local preview mode. Tasks are saved in this browser only.");
});
$("#close-dialog").addEventListener("click", () => aboutDialog.close());
aboutDialog.addEventListener("click", event => {
  if (event.target === aboutDialog) aboutDialog.close();
});

async function bootstrap() {
  try {
    const health = await api("/api/health");
    backendAvailable = health.status === "ok" && health.storage === "sqlite";
    if (backendAvailable && !localStorage.getItem(MIGRATION_KEY)) {
      await api("/api/import-local", { method: "POST", body: JSON.stringify({
        tasks: normalizeTasks(readJson(STORAGE_KEY, [])),
        activities: normalizeActivities(readJson(ACTIVITY_KEY, []))
      }) });
      localStorage.setItem(MIGRATION_KEY, "complete");
    }
    if (backendAvailable) await refreshFromServer();
  } catch {
    backendAvailable = false;
    tasks = normalizeTasks(readJson(STORAGE_KEY, []));
    activities = normalizeActivities(readJson(ACTIVITY_KEY, []));
  }
  renderConnection();
  render();
  if (tasks.length && !activities.length && !backendAvailable) logActivity("Workspace restored", `${tasks.length} task(s) loaded from this browser.`);
}

render();
bootstrap();
