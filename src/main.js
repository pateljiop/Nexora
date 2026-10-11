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
const modelSetupDialog = $("#model-setup-dialog");
let modelStatusSnapshot = null;
let currentView = "overview";
let backendAvailable = false;
let currentPlan = null;
let activeExecutionId = null;
let currentExecutionPlanId = null;
let currentChangeProposal = null;
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
    check.addEventListener("click", () => toggleTask(task.id).catch(error => showToast(error.message)));

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
    remove.addEventListener("click", () => removeTask(task.id).catch(error => showToast(error.message)));
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

function renderConnection() {
  $("#connection-dot").classList.toggle("muted", !backendAvailable);
  $("#connection-title").textContent = backendAvailable ? "Local storage connected" : "Local server not connected";
  $("#connection-subtitle").textContent = backendAvailable ? "SQLite · read-only tools only" : "Browser fallback · no execution";
  $(".orb-caption small").textContent = backendAvailable ? "LOCAL STORAGE READY" : "PREVIEW MODE";
  $(".notice").innerHTML = backendAvailable
    ? '<span>ⓘ</span> Local SQLite is connected. Model plans can only run allowlisted read-only tools. File changes require a saved diff proposal and separate approval; device control is disabled.'
    : '<span>ⓘ</span> Local server unavailable: tasks use this browser only. Start Nexora with run-local.bat. Model planning needs local configuration; device control is not connected.';
  const footer = $(".footer-state");
  if (footer) footer.lastChild.textContent = backendAvailable ? " LOCAL SQLITE" : " PREVIEW MODE";
}

function renderModelStatus(status = modelStatusSnapshot) {
  const dot = $("#model-status-dot");
  const state = $("#model-status-state");
  const summary = $("#model-status-summary");
  const detail = $("#model-setup-detail");
  const dialogStatus = $("#model-setup-status");
  if (!backendAvailable) {
    dot.classList.add("muted");
    state.textContent = "Offline";
    summary.textContent = "Start run-local.bat to check model settings.";
    dialogStatus.textContent = "The local server is not connected. Start Nexora, then refresh status.";
    detail.textContent = "No model configuration was read by this page.";
    return;
  }
  if (!status) {
    dot.classList.add("muted");
    state.textContent = "Unknown";
    summary.textContent = "Model status has not been checked yet.";
    dialogStatus.textContent = "Model status is not available yet.";
    detail.textContent = "Select Refresh status to query the local server.";
    return;
  }
  dot.classList.toggle("muted", !status.enabled);
  const label = status.enabled
    ? (status.remote ? "Remote enabled" : "Local enabled")
    : status.configured ? "Disabled" : "Not configured";
  state.textContent = label;
  summary.textContent = status.enabled
    ? (status.remote ? "Remote requests need per-goal confirmation." : "Local planning is enabled.")
    : status.configured ? "Settings found, but model requests are disabled." : "Optional: configure a local or remote model.";
  dialogStatus.textContent = status.enabled
    ? `Model planning is enabled (\${status.remote ? "remote provider" : "local endpoint"}).`
    : status.configured ? "Model settings are present but requests are disabled." : "No usable model configuration detected. The local template planner still works.";
  const details = [];
  if (status.providerHost) details.push(`Endpoint host: \${status.providerHost}`);
  if (status.model) details.push(`Model: \${status.model}`);
  details.push(status.remote
    ? "Privacy: the goal is sent externally only after per-request confirmation."
    : status.enabled ? "Privacy: goal stays on this laptop at the configured loopback endpoint." : "Privacy: no model request is currently enabled.");
  if (status.configurationError) details.push(status.configurationError);
  detail.replaceChildren(...details.map(line => makeElement("p", "", line)));
}

async function refreshModelStatus() {
  if (!backendAvailable) {
    modelStatusSnapshot = null;
    renderModelStatus(null);
    return;
  }
  try {
    modelStatusSnapshot = await api("/api/model/status");
    renderModelStatus();
  } catch {
    modelStatusSnapshot = null;
    $("#model-status-state").textContent = "Unavailable";
    $("#model-status-summary").textContent = "Could not read model status. Refresh to retry.";
    $("#model-setup-status").textContent = "Could not read model status from the local server.";
    $("#model-setup-detail").textContent = "No model request was made.";
  }
}

async function refreshFromServer() {
  const [taskPayload, activityPayload] = await Promise.all([api("/api/tasks"), api("/api/activity")]);
  tasks = normalizeTasks(taskPayload.tasks);
  activities = normalizeActivities(activityPayload.activities);
  render();
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

function renderPlan(plan) {
  currentPlan = plan;
  const runnable = ["local_model", "remote_model"].includes(plan.source) && plan.steps.length > 0 && plan.steps.every(step => ["workspace.list", "workspace.read", "workspace.diff", "tasks.list"].includes(step.tool));
  $("#run-plan-button").hidden = !runnable;
  const panel = $("#plan-preview");
  $("#plan-goal").textContent = plan.goal;
  const list = $("#plan-steps");
  list.replaceChildren();
  for (const step of plan.steps) {
    const item = makeElement("li", "plan-step");
    const copy = makeElement("div", "plan-step-copy");
    copy.append(makeElement("strong", "", step.title), makeElement("p", "", step.detail));
    if (step.tool) copy.append(makeElement("span", "tool-chip", step.tool));
    item.append(copy);
    list.append(item);
  }
  $(".plan-preview .stream-mark").textContent = plan.source === "remote_model" ? "REMOTE MODEL · DRY RUN" : plan.source === "local_model" ? "LOCAL MODEL · DRY RUN" : "LOCAL TEMPLATE · DRY RUN";
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function requestPlanPreview() {
  const goal = taskInput.value.trim();
  if (!goal) {
    showToast("Write a goal first, then preview a plan.");
    taskInput.focus();
    return;
  }
  if (!backendAvailable) {
    showToast("Start the local server with run-local.bat to create a saved plan preview.");
    return;
  }
  try {
    const modelStatus = await api("/api/model/status");
    let remoteConsent = false;
    let useModel = modelStatus.enabled && modelStatus.dataSharing === "local_goal_stays_on_laptop";
    if (modelStatus.enabled && modelStatus.dataSharing === "remote_goal_sent_only_with_per_request_confirmation") {
      remoteConsent = window.confirm(`This sends your goal to the configured external model (${modelStatus.providerHost}, ${modelStatus.model}). Continue? Choose Cancel to use the local template instead.`);
      useModel = remoteConsent;
    }
    const result = await api("/api/plans", { method: "POST", body: JSON.stringify({ goal, useModel, remoteConsent }) });
    renderPlan(result.plan);
    await refreshFromServer();
    showToast(result.plan.source === "remote_model" ? "Remote plan preview saved. No actions were executed." : result.plan.source === "local_model" ? "Local model plan saved. No actions were executed." : "Local template preview saved. No actions were executed.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not create the plan preview.");
  }
}

$("#model-setup-button").addEventListener("click", async () => {
  modelSetupDialog.showModal();
  await refreshModelStatus();
});
$("#close-model-setup").addEventListener("click", () => modelSetupDialog.close());
$("#close-model-setup-footer").addEventListener("click", () => modelSetupDialog.close());
$("#refresh-model-status").addEventListener("click", refreshModelStatus);
$("#plan-button").addEventListener("click", requestPlanPreview);
$("#run-plan-button").addEventListener("click", runCurrentPlan);
$("#cancel-run-button").addEventListener("click", cancelCurrentExecution);
$("#refresh-run-button").addEventListener("click", () => refreshExecutionStatus({ poll: true }).catch(error => showToast(error.message)));
$("#review-saved-plan-button").addEventListener("click", async () => {
  if (!currentExecutionPlanId) return;
  try {
    const result = await api("/api/plans/" + encodeURIComponent(currentExecutionPlanId));
    if (!result.plan) throw new Error("Saved plan was not found.");
    renderPlan(result.plan);
    showToast("Saved plan loaded for review. Nothing will run until you confirm the tool list again.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not load the saved plan.");
  }
});

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

function renderExecution(execution, scroll = true) {
  const panel = $("#execution-result");
  $("#execution-title").textContent = execution.status === "running" ? "Read-only run in progress" : execution.status === "completed" ? "Read-only run finished" : "Read-only run stopped";
  $("#execution-note").textContent = execution.verificationNote;
  $("#execution-note").classList.remove("error");
  $("#execution-status").textContent = execution.status.toUpperCase();
  const checkpointPanel = $("#execution-checkpoint");
  const checkpoint = execution.recoveryCheckpoint;
  checkpointPanel.replaceChildren();
  if (checkpoint) {
    const summary = makeElement("strong", "", `Checkpoint: ${checkpoint.completedStepCount} of ${checkpoint.totalStepCount} steps completed`);
    const details = makeElement("p", "", checkpoint.lastCompletedStep
      ? `Last confirmed step: ${checkpoint.lastCompletedStep.title} (step ${checkpoint.lastCompletedStep.ordinal}).`
      : "No step has a confirmed completed result.");
    checkpointPanel.append(summary, details);
    if (checkpoint.nextStep && checkpoint.reviewRequired) {
      checkpointPanel.append(makeElement("p", "", `Next candidate after review: ${checkpoint.nextStep.title} (step ${checkpoint.nextStep.ordinal}).`));
    }
    if (checkpoint.uncertainStepTitles.length) {
      checkpointPanel.append(makeElement("p", "checkpoint-warning", `Uncertain outcome needs review: ${checkpoint.uncertainStepTitles.join(", ")}.`));
    }
    checkpointPanel.append(makeElement("p", "checkpoint-safety", checkpoint.automaticResumeAllowed
      ? "Recovery policy permits continuation."
      : checkpoint.reviewRequired
        ? "Automatic resume is disabled. Review the saved plan and start a fresh run only after checking the recorded results."
        : checkpoint.recommendation === "monitor_current_run"
          ? "Run is active. Refresh status to observe progress; no duplicate run was started."
          : "No recovery action is needed. The overall goal remains unverified unless separate evidence says otherwise."));
    checkpointPanel.hidden = false;
  } else {
    checkpointPanel.hidden = true;
  }
  const list = $("#execution-steps");
  list.replaceChildren();
  for (const step of execution.steps) {
    const item = makeElement("article", `execution-step ${step.status}`);
    const head = makeElement("div", "execution-step-head");
    head.append(makeElement("strong", "", step.title), makeElement("span", "", `${step.tool} · ${step.status.toUpperCase()}`));
    item.append(head);
    if (step.error) item.append(makeElement("p", "", step.error));
    if (step.output) {
      item.append(makeElement("p", "", step.output.summary || "Tool output"));
      if (step.output.tool === "workspace.diff" && step.output.data) {
        const diff = step.output.data.diff || "(No textual differences.)";
        item.append(makeElement("pre", "execution-diff", diff));
        if (step.output.data.truncated) item.append(makeElement("p", "execution-output-note", "Diff preview truncated at the output safety limit."));
        item.append(makeElement("p", "execution-output-note", (step.output.data.created ? "Proposed new file" : "Proposed update") + " · " + step.output.data.proposedBytes + " bytes · preview only"));
        if (step.status === "completed" && typeof step.arguments?.path === "string" && typeof step.arguments?.content === "string") {
          const prepare = makeElement("button", "plan-button", "Prepare change for approval");
          prepare.type = "button";
          prepare.addEventListener("click", () => prepareWorkspaceChange(step.arguments.path, step.arguments.content));
          item.append(prepare);
        }
      } else {
        const pre = makeElement("pre", "", JSON.stringify(step.output.data ?? step.output, null, 2));
        item.append(pre);
      }
    }
    list.append(item);
  }
  panel.hidden = false;
  const running = execution.status === "running";
  currentExecutionPlanId = execution.planId;
  $("#cancel-run-button").hidden = !running;
  $("#refresh-run-button").hidden = !running;
  $("#review-saved-plan-button").hidden = running;
  if (scroll) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setExecutionStatusError(message) {
  const note = $("#execution-note");
  if (!note) return;
  note.textContent = message + " The saved run was not retried; use Refresh status to check its current state.";
  note.classList.add("error");
}

async function refreshExecutionStatus({ poll = false } = {}) {
  if (!activeExecutionId) return null;
  const id = activeExecutionId;
  const maxPolls = poll ? 120 : 1;
  let execution = null;
  for (let attempt = 0; attempt < maxPolls; attempt++) {
    let result;
    try {
      result = await api(`/api/executions/${encodeURIComponent(id)}`);
    } catch (error) {
      setExecutionStatusError("Could not refresh run status: " + (error instanceof Error ? error.message : "Local API unavailable."));
      throw error;
    }
    execution = result.execution;
    if (!execution) {
      const error = new Error("Execution record was not found.");
      setExecutionStatusError(error.message);
      throw error;
    }
    renderExecution(execution, false);
    if (execution.status !== "running") {
      activeExecutionId = null;
      $("#cancel-run-button").hidden = true;
      $("#refresh-run-button").hidden = true;
      $("#run-plan-button").disabled = false;
      $("#run-plan-button").textContent = "Run read-only steps ↗";
      showToast(execution.status === "completed" ? "Read-only steps finished; the overall goal is still unverified." : `Run ended with status: ${execution.status}. Review the step report.`);
      await loadExecutionHistory();
      return execution;
    }
    if (!poll) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  $("#cancel-run-button").hidden = !activeExecutionId;
  $("#refresh-run-button").hidden = !activeExecutionId;
  if (activeExecutionId) showToast("Run is still in progress. You can cancel it or refresh its status.");
  return execution;
}

async function cancelCurrentExecution() {
  if (!activeExecutionId) return;
  const button = $("#cancel-run-button");
  button.disabled = true;
  try {
    const result = await api(`/api/executions/${encodeURIComponent(activeExecutionId)}/cancel`, { method: "POST", body: JSON.stringify({}) });
    showToast(result.execution.cancelRequested ? "Cancellation requested. The current read-only step may finish first." : "This run has already stopped.");
    await refreshExecutionStatus({ poll: true });
  } catch (error) {
    setExecutionStatusError("Could not confirm cancellation: " + (error instanceof Error ? error.message : "Local API unavailable."));
    showToast(error instanceof Error ? error.message : "Could not cancel this run.");
  } finally {
    button.disabled = false;
  }
}

async function runCurrentPlan() {
  if (!currentPlan || $("#run-plan-button").disabled || activeExecutionId) return;
  const selectedSteps = currentPlan.steps.filter(step => step.tool && step.tool !== "none");
  if (!selectedSteps.length || selectedSteps.length !== currentPlan.steps.length) {
    showToast("This plan contains steps without an approved read-only tool. Nothing was run.");
    return;
  }
  const toolSummary = selectedSteps.map((step, index) => {
    const args = step.arguments && Object.keys(step.arguments).length
      ? " (" + Object.entries(step.arguments).map(([key, value]) => key + "=" + String(value)).join(", ") + ")"
      : "";
    return (index + 1) + ". " + step.tool + args;
  }).join("\n");
  const approved = window.confirm(
    "Review the read-only run before continuing.\n\nGoal: " + currentPlan.goal +
    "\n\nTools and arguments:\n" + toolSummary +
    "\n\nOnly the configured workspace and saved task list can be read. No files will be written, deleted, or executed. Continue?"
  );
  if (!approved) {
    showToast("Run cancelled. No tools were called.");
    return;
  }
  const button = $("#run-plan-button");
  button.disabled = true;
  button.textContent = "Starting read-only tools…";
  try {
    const result = await api("/api/executions", { method: "POST", body: JSON.stringify({ planId: currentPlan.id }) });
    activeExecutionId = result.execution.id;
    $("#cancel-run-button").hidden = false;
    $("#refresh-run-button").hidden = false;
    renderExecution(result.execution);
    await refreshExecutionStatus({ poll: true });
    await refreshFromServer();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not start the read-only plan.");
  } finally {
    if (!activeExecutionId) {
      button.disabled = false;
      button.textContent = "Run read-only steps ↗";
    } else {
      button.disabled = true;
      button.textContent = "Run in progress…";
    }
  }
}

async function loadExecutionHistory() {
  const list = $("#execution-history-list");
  if (!backendAvailable) {
    list.replaceChildren(makeElement("p", "workspace-empty", "Start the local server to view saved runs."));
    return;
  }
  try {
    const result = await api("/api/executions");
    list.replaceChildren();
    if (!result.executions.length) {
      list.append(makeElement("p", "workspace-empty", "No read-only runs have been recorded yet."));
      return;
    }
    const runningExecution = result.executions.find(execution => execution.status === "running");
    for (const execution of result.executions) {
      const button = makeElement("button", "execution-history-item");
      button.type = "button";
      const copy = makeElement("span", "execution-history-copy");
      copy.append(makeElement("strong", "", execution.goal),
        makeElement("small", "", `${execution.steps.length} step(s) · ${formatTime(execution.createdAt)}`));
      const status = makeElement("span", `execution-history-status ${execution.status}`, execution.status.toUpperCase());
      button.append(copy, status);
      button.addEventListener("click", async () => {
        if (activeExecutionId && activeExecutionId !== execution.id) {
          showToast("Another run is active. Keep its controls selected until it stops.");
          return;
        }
        try {
          const detail = await api(`/api/executions/${encodeURIComponent(execution.id)}`);
          activeExecutionId = detail.execution.status === "running" ? detail.execution.id : null;
          renderExecution(detail.execution);
          if (activeExecutionId) await refreshExecutionStatus({ poll: true });
        } catch (error) {
          showToast(error instanceof Error ? error.message : "Could not load saved run.");
        }
      });
      list.append(button);
    }
    if (runningExecution && !activeExecutionId) {
      const detail = await api(`/api/executions/${encodeURIComponent(runningExecution.id)}`);
      if (detail.execution?.status === "running") {
        activeExecutionId = detail.execution.id;
        $("#cancel-run-button").hidden = false;
        $("#refresh-run-button").hidden = false;
        $("#run-plan-button").disabled = true;
        $("#run-plan-button").textContent = "Run in progress…";
        renderExecution(detail.execution, false);
        void refreshExecutionStatus({ poll: true }).catch(error => showToast(error.message));
      }
    }
  } catch (error) {
    list.replaceChildren(makeElement("p", "workspace-empty", error instanceof Error ? error.message : "Could not load run history."));
  }
}

$("#refresh-execution-history").addEventListener("click", loadExecutionHistory);

function renderWorkspaceChange(change) {
  currentChangeProposal = change;
  const panel = $("#workspace-change-review");
  panel.hidden = false;
  $("#workspace-change-status").textContent = change.status.toUpperCase();
  $("#workspace-change-status").className = "execution-history-status " + change.status;
  $("#workspace-change-path").textContent = change.path + (change.created ? " · new file" : " · existing file");
  $("#workspace-change-diff").textContent = change.diff || "(No textual differences.)";
  $("#workspace-change-note").textContent = change.status === "pending"
    ? "No file has been changed. Review the entire diff above; applying creates a backup for existing files."
    : change.status === "applied"
      ? (change.error || "The change was applied after explicit approval. A verified backup receipt is recorded for rollback.")
      : change.status === "rolled_back"
        ? "The approved change was rolled back. The saved record is retained for audit."
        : change.status === "stale"
          ? "The target changed after this proposal was created. It was not overwritten; create a fresh proposal."
          : change.status === "failed" || change.status === "applying"
            ? (change.error || "The change needs manual review. No automatic retry will occur.")
            : "Saved change proposal.";
  $("#apply-workspace-change").hidden = change.status !== "pending";
  $("#rollback-workspace-change").hidden = change.status !== "applied";
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function prepareWorkspaceChange(path, content) {
  try {
    const result = await api("/api/workspace/changes", {
      method: "POST",
      body: JSON.stringify({ path, content })
    });
    renderWorkspaceChange(result.change);
    await loadWorkspaceChanges(result.change.id);
    showToast("Full diff saved for review. No file has been changed.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not prepare the change proposal.");
  }
}

async function loadWorkspaceChanges(selectedId = null) {
  const list = $("#workspace-change-history");
  if (!backendAvailable) {
    list.replaceChildren(makeElement("p", "workspace-empty", "Start the local server to view saved change proposals."));
    return;
  }
  try {
    const result = await api("/api/workspace/changes");
    list.replaceChildren();
    if (!result.changes.length) {
      list.append(makeElement("p", "workspace-empty", "No saved change proposals yet."));
      return;
    }
    for (const change of result.changes) {
      const button = makeElement("button", "workspace-change-history-item");
      button.type = "button";
      const copy = makeElement("span", "workspace-change-history-copy");
      copy.append(makeElement("strong", "", change.path),
        makeElement("small", "", formatTime(change.createdAt)));
      button.append(copy, makeElement("span", "execution-history-status " + change.status, change.status.toUpperCase()));
      button.addEventListener("click", async () => {
        try {
          const detail = await api("/api/workspace/changes/" + encodeURIComponent(change.id));
          if (detail.change) renderWorkspaceChange(detail.change);
        } catch (error) {
          showToast(error instanceof Error ? error.message : "Could not load change proposal.");
        }
      });
      list.append(button);
    }
    const targetId = selectedId || currentChangeProposal?.id || result.changes[0].id;
    const target = result.changes.find(change => change.id === targetId);
    if (target) {
      const detail = await api("/api/workspace/changes/" + encodeURIComponent(target.id));
      if (detail.change) {
        renderWorkspaceChange(detail.change);
      }
    }
  } catch (error) {
    list.replaceChildren(makeElement("p", "workspace-empty", error instanceof Error ? error.message : "Could not load change history."));
  }
}

async function applyWorkspaceChange() {
  if (!currentChangeProposal || currentChangeProposal.status !== "pending") return;
  const change = currentChangeProposal;
  const approved = window.confirm(
    "Apply the complete diff currently shown for " + change.path + "?\n\n" +
    "Nexora will verify the file has not changed since this preview and create a backup before replacing it. " +
    "If the file changed, the operation will stop. Continue?"
  );
  if (!approved) return;
  $("#apply-workspace-change").disabled = true;
  try {
    const result = await api("/api/workspace/changes/" + encodeURIComponent(change.id) + "/apply", {
      method: "POST", body: JSON.stringify({ approved: true })
    });
    renderWorkspaceChange(result.change);
    await loadWorkspaceChanges(change.id);
    await loadWorkspace(change.path.split("/").slice(0, -1).join("/") || ".");
    showToast("Approved change applied; backup receipt recorded.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not apply the reviewed change.");
    await loadWorkspaceChanges(change.id);
  } finally {
    $("#apply-workspace-change").disabled = false;
  }
}

async function rollbackWorkspaceChange() {
  if (!currentChangeProposal || currentChangeProposal.status !== "applied") return;
  const change = currentChangeProposal;
  const approved = window.confirm(
    "Roll back Nexora's change to " + change.path + "?\n\n" +
    "Rollback will proceed only if the file still matches the exact content Nexora wrote. Later edits will be preserved."
  );
  if (!approved) return;
  $("#rollback-workspace-change").disabled = true;
  try {
    const result = await api("/api/workspace/changes/" + encodeURIComponent(change.id) + "/rollback", {
      method: "POST", body: JSON.stringify({ approved: true })
    });
    renderWorkspaceChange(result.change);
    await loadWorkspaceChanges(change.id);
    await loadWorkspace(change.path.split("/").slice(0, -1).join("/") || ".");
    showToast("Rollback completed and recorded.");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not roll back the change.");
    await loadWorkspaceChanges(change.id);
  } finally {
    $("#rollback-workspace-change").disabled = false;
  }
}

$("#apply-workspace-change").addEventListener("click", applyWorkspaceChange);
$("#rollback-workspace-change").addEventListener("click", rollbackWorkspaceChange);
$("#refresh-workspace-changes").addEventListener("click", () => loadWorkspaceChanges());

async function readWorkspaceFile(relativePath) {
  try {
    const result = await api(`/api/workspace/read?path=${encodeURIComponent(relativePath)}`);
    $("#workspace-preview-path").textContent = result.path;
    $("#workspace-file-content").textContent = result.content;
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Could not preview that file.");
  }
}

async function loadWorkspace(relativePath = ".") {
  const list = $("#workspace-file-list");
  if (!backendAvailable) {
    list.replaceChildren(makeElement("p", "workspace-empty", "Start the local server with run-local.bat to inspect files."));
    $("#workspace-location").textContent = "Local server disconnected.";
    return;
  }
  try {
    const result = await api(`/api/workspace?path=${encodeURIComponent(relativePath)}`);
    list.replaceChildren();
    const current = result.relativePath || ".";
    $("#workspace-location").textContent = `${result.rootName} / ${current} · read-only · no files changed`;
    if (current !== ".") {
      const up = makeElement("button", "workspace-file-button");
      up.type = "button";
      up.append(makeElement("span", "file-glyph", "↰"), makeElement("span", "file-path", "Go up"));
      const parts = current.split("/");
      parts.pop();
      up.addEventListener("click", () => loadWorkspace(parts.length ? parts.join("/") : "."));
      list.append(up);
    }
    if (!result.entries.length) list.append(makeElement("p", "workspace-empty", "No visible files or folders here."));
    for (const entry of result.entries) {
      const button = makeElement("button", "workspace-file-button");
      button.type = "button";
      button.title = entry.path;
      button.append(makeElement("span", "file-glyph", entry.kind === "directory" ? "▸" : "⌑"),
        makeElement("span", "file-path", entry.path));
      button.addEventListener("click", () => entry.kind === "directory" ? loadWorkspace(entry.path) : readWorkspaceFile(entry.path));
      list.append(button);
    }
    if (result.truncated) list.append(makeElement("p", "workspace-empty", "Listing capped at 200 entries."));
  } catch (error) {
    list.replaceChildren(makeElement("p", "workspace-empty", error instanceof Error ? error.message : "Workspace listing failed."));
  }
}

$("#refresh-workspace").addEventListener("click", () => loadWorkspace("."));

let screenStream = null;
let capturedFrameDataUrl = null;

function setScreenObserverMessage(message, isError = false) {
  const element = $("#screen-observer-message");
  element.textContent = message;
  element.classList.toggle("error", isError);
}

async function startScreenShare() {
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getDisplayMedia !== "function") {
    setScreenObserverMessage("Screen sharing is not supported by this browser. Open Nexora in a current desktop browser over localhost.", true);
    return;
  }
  const start = $("#start-screen-share");
  start.disabled = true;
  try {
    // Browser-managed picker and permission are required on every new share.
    screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    const video = $("#screen-live-video");
    video.srcObject = screenStream;
    video.hidden = false;
    $("#screen-observer-placeholder").hidden = true;
    await video.play();
    $("#screen-share-status").textContent = "SHARING LOCALLY";
    $("#stop-screen-share").hidden = false;
    $("#capture-screen-frame").disabled = false;
    start.hidden = true;
    setScreenObserverMessage("Screen is visible in this browser only. Nothing is sent to a model unless you click Analyze and confirm.");
    const [track] = screenStream.getVideoTracks();
    if (track) track.addEventListener("ended", stopScreenShare, { once: true });
  } catch (error) {
    screenStream?.getTracks().forEach(track => track.stop());
    screenStream = null;
    $("#screen-live-video").srcObject = null;
    $("#screen-live-video").hidden = true;
    $("#screen-observer-placeholder").hidden = false;
    $("#screen-share-status").textContent = "NOT SHARING";
    $("#stop-screen-share").hidden = true;
    $("#capture-screen-frame").disabled = true;
    start.hidden = false;
    setScreenObserverMessage(error?.name === "NotAllowedError"
      ? "Screen sharing was cancelled or permission was denied. Nothing is being captured."
      : "Could not start screen sharing. Check browser support and try again.", true);
  } finally {
    start.disabled = false;
  }
}

function captureScreenFrame() {
  const video = $("#screen-live-video");
  if (!screenStream || !video.videoWidth || !video.videoHeight) {
    setScreenObserverMessage("Wait until the shared screen is visible, then capture a frame.", true);
    return;
  }
  const scale = Math.min(1, 1280 / video.videoWidth, 720 / video.videoHeight);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  try {
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.62);
    if (dataUrl.length > 1_300_000) {
      setScreenObserverMessage("Captured frame is too large to analyze safely. Reduce the shared display resolution and capture again.", true);
      return;
    }
    capturedFrameDataUrl = dataUrl;
    $("#screen-frame-image").src = dataUrl;
    $("#screen-frame-result").hidden = false;
    $("#analyze-screen-frame").disabled = false;
    $("#screen-analysis-result").hidden = true;
    setScreenObserverMessage("Frame captured in browser memory. It is not saved or sent unless you choose Analyze and confirm.");
  } catch {
    capturedFrameDataUrl = null;
    $("#analyze-screen-frame").disabled = true;
    setScreenObserverMessage("Could not capture this frame. The active screen share remains unchanged.", true);
  }
}

async function analyzeScreenFrame() {
  if (!capturedFrameDataUrl) {
    setScreenObserverMessage("Capture a frame first, then choose Analyze with model.", true);
    return;
  }
  if (!backendAvailable) {
    setScreenObserverMessage("Start Nexora with run-local.bat before requesting model analysis.", true);
    return;
  }
  let modelStatus;
  try {
    modelStatus = await api("/api/model/status");
  } catch {
    setScreenObserverMessage("Could not check model configuration. No screenshot was sent.", true);
    return;
  }
  if (!modelStatus.enabled) {
    setScreenObserverMessage("Model analysis is disabled. Configure a local model or explicitly enable a remote provider in .env, then restart Nexora.", true);
    return;
  }
  const question = $("#screen-analysis-question").value.trim();
  const destination = modelStatus.remote
    ? `external provider \${modelStatus.providerHost} (\${modelStatus.model})`
    : `local model endpoint \${modelStatus.providerHost} (\${modelStatus.model})`;
  const consentMessage = modelStatus.remote
    ? `This sends the captured screenshot and your question to the \${destination}. The image may contain private information. Continue?`
    : `This sends the captured screenshot and your question to the \${destination}. The frame will not be saved by Nexora. Continue?`;
  if (!window.confirm(consentMessage)) {
    setScreenObserverMessage("Analysis cancelled. The screenshot remains in browser memory and was not sent.");
    return;
  }
  const button = $("#analyze-screen-frame");
  button.disabled = true;
  button.textContent = "Analyzing…";
  try {
    const result = await api("/api/screen/analyze", {
      method: "POST",
      body: JSON.stringify({ consent: true, remoteConsent: modelStatus.remote ? true : false,
        imageDataUrl: capturedFrameDataUrl, question })
    });
    $("#screen-analysis-text").textContent = result.analysis;
    $("#screen-analysis-source").textContent = result.remote
      ? `Remote · \${result.providerHost} · \${result.model}`
      : `Local · \${result.providerHost} · \${result.model}`;
    $("#screen-analysis-result").hidden = false;
    setScreenObserverMessage("Analysis finished. The frame and response were not saved to Nexora's database or activity log.");
  } catch (error) {
    setScreenObserverMessage(error instanceof Error ? error.message : "Screen analysis failed. No action was performed.", true);
  } finally {
    button.textContent = "Analyze with model ↗";
    button.disabled = !capturedFrameDataUrl;
  }
}

function stopScreenShare() {
  const stream = screenStream;
  screenStream = null;
  stream?.getTracks().forEach(track => track.stop());
  const video = $("#screen-live-video");
  if (video) {
    video.pause();
    video.srcObject = null;
    video.hidden = true;
  }
  const placeholder = $("#screen-observer-placeholder");
  if (placeholder) placeholder.hidden = false;
  const status = $("#screen-share-status");
  if (status) status.textContent = "NOT SHARING";
  const start = $("#start-screen-share");
  if (start) start.hidden = false;
  const stop = $("#stop-screen-share");
  if (stop) stop.hidden = true;
  const capture = $("#capture-screen-frame");
  if (capture) capture.disabled = true;
  capturedFrameDataUrl = null;
  const frameImage = $("#screen-frame-image");
  if (frameImage) frameImage.removeAttribute("src");
  const frameResult = $("#screen-frame-result");
  if (frameResult) frameResult.hidden = true;
  const analyzeButton = $("#analyze-screen-frame");
  if (analyzeButton) analyzeButton.disabled = true;
  const analysisResult = $("#screen-analysis-result");
  if (analysisResult) analysisResult.hidden = true;
  const analysisText = $("#screen-analysis-text");
  if (analysisText) analysisText.textContent = "";
  if (document.querySelector("#screen-observer-message")) {
    setScreenObserverMessage("Screen sharing stopped. The captured frame and analysis preview were cleared.");
  }
}

$("#start-screen-share").addEventListener("click", startScreenShare);
$("#capture-screen-frame").addEventListener("click", captureScreenFrame);
$("#analyze-screen-frame").addEventListener("click", analyzeScreenFrame);
$("#stop-screen-share").addEventListener("click", stopScreenShare);
window.addEventListener("pagehide", () => {
  stopScreenShare();
  $("#screen-frame-image").removeAttribute("src");
  $("#screen-frame-result").hidden = true;
});

async function bootstrap() {
  try {
    const health = await api("/api/health");
    backendAvailable = health.status === "ok" && health.storage === "sqlite";
    if (backendAvailable && !localStorage.getItem(MIGRATION_KEY)) {
      const legacyTasks = normalizeTasks(readJson(STORAGE_KEY, []));
      const legacyActivities = normalizeActivities(readJson(ACTIVITY_KEY, []));
      for (let offset = 0; offset < legacyTasks.length || offset === 0; offset += 20) {
        await api("/api/import-local", { method: "POST", body: JSON.stringify({
          tasks: legacyTasks.slice(offset, offset + 20),
          activities: offset === 0 ? legacyActivities : []
        }) });
        if (legacyTasks.length === 0) break;
      }
      localStorage.setItem(MIGRATION_KEY, "complete");
    }
    if (backendAvailable) await refreshFromServer();
  } catch {
    backendAvailable = false;
    tasks = normalizeTasks(readJson(STORAGE_KEY, []));
    activities = normalizeActivities(readJson(ACTIVITY_KEY, []));
  }
  renderConnection();
  renderModelStatus();
  render();
  await refreshModelStatus();
  await loadWorkspace(".");
  await loadExecutionHistory();
  await loadWorkspaceChanges();
  if (tasks.length && !activities.length && !backendAvailable) logActivity("Workspace restored", `${tasks.length} task(s) loaded from this browser.`);
}

render();
bootstrap();
