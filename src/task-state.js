export const MAX_TASK_LENGTH = 1200;
export const TASK_STATUSES = Object.freeze(["pending", "completed"]);

export function createTask(title, now = new Date(), id = makeId()) {
  if (typeof title !== "string") throw new TypeError("Task title must be a string.");
  const cleanTitle = title.trim();
  if (!cleanTitle) throw new Error("Write a task before adding it.");
  if (cleanTitle.length > MAX_TASK_LENGTH) throw new Error(`Task must be ${MAX_TASK_LENGTH} characters or fewer.`);
  const createdAt = now instanceof Date ? now.toISOString() : new Date(now).toISOString();
  return { id, title: cleanTitle, status: "pending", createdAt, updatedAt: createdAt };
}

export function setTaskStatus(tasks, id, status, now = new Date()) {
  if (!TASK_STATUSES.includes(status)) throw new Error("Unsupported task status.");
  const timestamp = now instanceof Date ? now.toISOString() : new Date(now).toISOString();
  return tasks.map(task => task.id === id ? { ...task, status, updatedAt: timestamp } : task);
}

export function deleteTask(tasks, id) {
  return tasks.filter(task => task.id !== id);
}

export function summarizeTasks(tasks) {
  return {
    total: tasks.length,
    pending: tasks.filter(task => task.status === "pending").length,
    completed: tasks.filter(task => task.status === "completed").length,
    running: 0,
    approvals: 0
  };
}

export function isValidTask(value) {
  return Boolean(value && typeof value === "object" &&
    typeof value.id === "string" && value.id.length > 0 &&
    typeof value.title === "string" && value.title.trim().length > 0 &&
    TASK_STATUSES.includes(value.status) &&
    typeof value.createdAt === "string" &&
    !Number.isNaN(Date.parse(value.createdAt)));
}

export function normalizeTasks(value) {
  if (!Array.isArray(value)) return [];
  return value.filter(isValidTask).slice(0, 500).map(task => ({
    id: task.id,
    title: task.title.trim().slice(0, MAX_TASK_LENGTH),
    status: task.status,
    createdAt: task.createdAt,
    updatedAt: typeof task.updatedAt === "string" && !Number.isNaN(Date.parse(task.updatedAt)) ? task.updatedAt : task.createdAt
  }));
}

function makeId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
  return `task-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}