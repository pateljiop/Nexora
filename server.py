"""Local-only HTTP API and static server for Nexora / Virtual Hariom."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from planner import build_dry_run_plan, validate_plan
from model_provider import ModelProviderError, build_model_plan, get_model_status
from workspace_tools import Workspace, WorkspaceError
from execution_engine import ExecutionError, run_plan_execution

ROOT = Path(__file__).resolve().parent

def load_local_env():
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value

load_local_env()
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "nexora.sqlite3"
HOST = "127.0.0.1"
PORT = int(os.environ.get("NEXORA_PORT", "8765"))
MAX_BODY = 64 * 1024
MAX_TASKS = 500
MAX_ACTIVITY = 30
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
STATUSES = {"pending", "completed"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 1200),
                status TEXT NOT NULL CHECK(status IN ('pending', 'completed')),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL CHECK(length(message) BETWEEN 1 AND 180),
                detail TEXT NOT NULL DEFAULT '', at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, goal TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, goal TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'blocked', 'cancelled')),
                goal_verified INTEGER NOT NULL DEFAULT 0, verification_note TEXT NOT NULL,
                created_at TEXT NOT NULL, finished_at TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS execution_steps (
                id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                plan_step_id TEXT NOT NULL, title TEXT NOT NULL, tool TEXT NOT NULL,
                arguments_json TEXT NOT NULL, status TEXT NOT NULL,
                output_json TEXT, error TEXT, started_at TEXT, finished_at TEXT,
                FOREIGN KEY(execution_id) REFERENCES executions(id) ON DELETE CASCADE)""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def valid_time(value):
        if not isinstance(value, str) or len(value) > 40:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    @staticmethod
    def task_dict(row):
        return {"id": row["id"], "title": row["title"], "status": row["status"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def list_tasks(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,title,status,created_at,updated_at FROM tasks ORDER BY created_at DESC,rowid DESC LIMIT ?", (MAX_TASKS,)).fetchall()
        return [self.task_dict(row) for row in rows]

    def add_activity(self, message, detail=""):
        message, detail = str(message).strip()[:180], str(detail or "")[:220]
        if not message:
            return
        with self.connect() as db:
            db.execute("INSERT INTO activity(message,detail,at) VALUES(?,?,?)", (message, detail, now_iso()))
            db.execute("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT ?)", (MAX_ACTIVITY,))

    def list_activity(self):
        with self.connect() as db:
            rows = db.execute("SELECT message,detail,at FROM activity ORDER BY id DESC LIMIT ?", (MAX_ACTIVITY,)).fetchall()
        return [dict(row) for row in rows]

    def task_exists(self, task_id):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone() is not None

    def create_task(self, title, task_id=None, created_at=None, updated_at=None, status="pending"):
        if not isinstance(title, str):
            raise ValueError("Task title must be a string.")
        title = title.strip()
        if not title:
            raise ValueError("Write a task before adding it.")
        if len(title) > 1200:
            raise ValueError("Task must be 1200 characters or fewer.")
        task_id = task_id or str(uuid.uuid4())
        if not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("Invalid task id.")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Unsupported task status.")
        created_at = created_at if self.valid_time(created_at) else now_iso()
        updated_at = updated_at if self.valid_time(updated_at) else created_at
        with self.connect() as db:
            db.execute("INSERT INTO tasks(id,title,status,created_at,updated_at) VALUES(?,?,?,?,?)",
                       (task_id, title, status, created_at, updated_at))
        return {"id": task_id, "title": title, "status": status, "createdAt": created_at, "updatedAt": updated_at}

    def update_task(self, task_id, status):
        if not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("Invalid task id.")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Unsupported task status.")
        with self.connect() as db:
            cursor = db.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, now_iso(), task_id))
            row = db.execute("SELECT id,title,status,created_at,updated_at FROM tasks WHERE id=?", (task_id,)).fetchone()
        if cursor.rowcount:
            self.add_activity("Task marked complete" if status == "completed" else "Task reopened", row["title"])
        return self.task_dict(row) if row else None

    def delete_task(self, task_id):
        if not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("Invalid task id.")
        with self.connect() as db:
            row = db.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
            cursor = db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        if cursor.rowcount:
            self.add_activity("Task removed", row["title"])
        return bool(cursor.rowcount)

    def import_local(self, tasks, activities):
        if not isinstance(tasks, list) or not isinstance(activities, list):
            raise ValueError("Tasks and activities must be arrays.")
        imported = 0
        for item in tasks[:MAX_TASKS]:
            if not isinstance(item, dict):
                continue
            task_id = item.get("id")
            if not isinstance(task_id, str) or not ID_PATTERN.fullmatch(task_id) or self.task_exists(task_id):
                continue
            try:
                self.create_task(item.get("title"), task_id, item.get("createdAt"), item.get("updatedAt"), item.get("status", "pending"))
                imported += 1
            except (ValueError, sqlite3.IntegrityError):
                continue
        for item in activities[:MAX_ACTIVITY]:
            if not isinstance(item, dict) or not isinstance(item.get("message"), str):
                continue
            message, detail, at = item["message"].strip()[:180], str(item.get("detail") or "")[:220], item.get("at")
            if message and self.valid_time(at):
                with self.connect() as db:
                    exists = db.execute("SELECT 1 FROM activity WHERE message=? AND detail=? AND at=?", (message, detail, at)).fetchone()
                    if not exists:
                        db.execute("INSERT INTO activity(message,detail,at) VALUES(?,?,?)", (message, detail, at))
        with self.connect() as db:
            db.execute("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT ?)", (MAX_ACTIVITY,))
        return imported


    def save_plan(self, plan):
        plan = validate_plan(plan)
        with self.connect() as db:
            db.execute("INSERT INTO plans(id,goal,payload_json,created_at) VALUES(?,?,?,?)",
                       (plan["id"], plan["goal"], json.dumps(plan, ensure_ascii=False), plan["createdAt"]))
            db.execute("DELETE FROM plans WHERE id NOT IN (SELECT id FROM plans ORDER BY created_at DESC LIMIT 200)")
        self.add_activity("Plan preview created", plan["goal"])
        return plan

    def create_plan(self, goal):
        return self.save_plan(validate_plan(build_dry_run_plan(goal)))

    def list_plans(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload_json FROM plans ORDER BY created_at DESC LIMIT 50").fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_plan(self, plan_id):
        if not isinstance(plan_id, str) or not ID_PATTERN.fullmatch(plan_id):
            return None
        with self.connect() as db:
            row = db.execute("SELECT payload_json FROM plans WHERE id=?", (plan_id,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def start_execution(self, plan, steps):
        execution_id = str(uuid.uuid4())
        created = now_iso()
        note = "Read-only tool steps completed; the user's overall goal has not been independently verified."
        with self.connect() as db:
            db.execute("INSERT INTO executions(id,plan_id,goal,status,goal_verified,verification_note,created_at) VALUES(?,?,?,'running',0,?,?)",
                       (execution_id, plan["id"], plan["goal"], note, created))
            for ordinal, step in enumerate(steps, start=1):
                db.execute("INSERT INTO execution_steps(id,execution_id,ordinal,plan_step_id,title,tool,arguments_json,status) VALUES(?,?,?,?,?,?,?,'not_started')",
                           (str(uuid.uuid4()), execution_id, ordinal, step["id"], step["title"], step["tool"],
                            json.dumps(step.get("arguments", {}), ensure_ascii=False)))
        return self.get_execution(execution_id)

    def set_execution_step_status(self, execution_id, plan_step_id, status):
        if status not in {"not_started", "running", "completed", "failed", "skipped"}:
            raise ValueError("Unsupported execution step status.")
        started = now_iso() if status == "running" else None
        with self.connect() as db:
            db.execute("UPDATE execution_steps SET status=?, started_at=COALESCE(started_at, ?) WHERE execution_id=? AND plan_step_id=?",
                       (status, started, execution_id, plan_step_id))

    def finish_execution_step(self, execution_id, plan_step_id, status, output=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE execution_steps SET status=?, output_json=?, error=?, finished_at=? WHERE execution_id=? AND plan_step_id=?",
                       (status, json.dumps(output, ensure_ascii=False) if output is not None else None,
                        error[:500] if error else None, now_iso(), execution_id, plan_step_id))

    def finish_execution(self, execution_id, status):
        if status not in {"completed", "failed", "blocked", "cancelled"}:
            raise ValueError("Unsupported execution status.")
        note = ("Read-only tool steps completed; the user's overall goal has not been independently verified."
                if status == "completed" else
                "The read-only run stopped before all steps completed; the user's overall goal has not been independently verified.")
        with self.connect() as db:
            db.execute("UPDATE executions SET status=?, finished_at=?, verification_note=? WHERE id=?",
                       (status, now_iso(), note, execution_id))

    def get_execution(self, execution_id):
        if not isinstance(execution_id, str) or not ID_PATTERN.fullmatch(execution_id):
            return None
        with self.connect() as db:
            row = db.execute("SELECT * FROM executions WHERE id=?", (execution_id,)).fetchone()
            if not row:
                return None
            step_rows = db.execute("SELECT * FROM execution_steps WHERE execution_id=? ORDER BY ordinal", (execution_id,)).fetchall()
        steps = []
        for item in step_rows:
            steps.append({"id": item["plan_step_id"], "title": item["title"], "tool": item["tool"],
                          "arguments": json.loads(item["arguments_json"]), "status": item["status"],
                          "output": json.loads(item["output_json"]) if item["output_json"] else None,
                          "error": item["error"], "startedAt": item["started_at"], "finishedAt": item["finished_at"]})
        return {"id": row["id"], "planId": row["plan_id"], "goal": row["goal"], "status": row["status"],
                "goalVerified": bool(row["goal_verified"]), "verificationNote": row["verification_note"],
                "createdAt": row["created_at"], "finishedAt": row["finished_at"], "steps": steps}

    def list_executions(self):
        with self.connect() as db:
            rows = db.execute("SELECT id FROM executions ORDER BY created_at DESC LIMIT 20").fetchall()
        return [self.get_execution(row["id"]) for row in rows]

class Handler(BaseHTTPRequestHandler):
    server_version = "NexoraLocal/1.0"
    store = None
    workspace = None

    def log_message(self, fmt, *args):
        print("[Nexora]", self.address_string(), fmt % args)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def safe_request(self):
        port = self.server.server_port
        if self.headers.get("Host", "") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self.send_json(403, {"error": "Request host is not allowed."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self.send_json(403, {"error": "Request origin is not allowed."})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_json(403, {"error": "Cross-site requests are not allowed."})
            return False
        return True

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise ValueError("A valid Content-Length header is required.")
        if length < 0 or length > MAX_BODY:
            raise ValueError("Request body is too large.")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Request body must be valid JSON.")
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    def do_GET(self):
        if not self.safe_request():
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self.send_json(200, {"status": "ok", "storage": "sqlite", "execution": "disabled"})
            elif path == "/api/tasks":
                self.send_json(200, {"tasks": self.store.list_tasks()})
            elif path == "/api/activity":
                self.send_json(200, {"activities": self.store.list_activity()})
            elif path == "/api/plans":
                self.send_json(200, {"plans": self.store.list_plans()})
            elif path == "/api/model/status":
                self.send_json(200, get_model_status())
            elif path == "/api/workspace":
                relative = parse_qs(urlparse(self.path).query).get("path", ["."])[0]
                try:
                    self.send_json(200, self.workspace.list_files(relative))
                except WorkspaceError as exc:
                    self.send_json(400, {"error": str(exc)})
            elif path == "/api/workspace/read":
                relative = parse_qs(urlparse(self.path).query).get("path", [""])[0]
                try:
                    self.send_json(200, self.workspace.read_file(relative))
                except WorkspaceError as exc:
                    self.send_json(400, {"error": str(exc)})
            elif path == "/api/executions":
                self.send_json(200, {"executions": self.store.list_executions()})
            elif re.fullmatch(r"/api/executions/[^/]+", path):
                execution = self.store.get_execution(unquote(path.rsplit("/", 1)[-1]))
                self.send_json(200, {"execution": execution}) if execution else self.send_json(404, {"error": "Execution not found."})
            elif path.startswith("/api/"):
                self.send_json(404, {"error": "API route not found."})
            else:
                self.serve_static(path)
        except (OSError, sqlite3.Error):
            self.send_json(500, {"error": "Local storage could not complete the request."})

    def do_POST(self):
        if not self.safe_request():
            return
        try:
            payload = self.read_json()
            path = urlparse(self.path).path
            if path == "/api/tasks":
                task = self.store.create_task(payload.get("title"))
                self.store.add_activity("Task added to your workspace", task["title"])
                self.send_json(201, {"task": task})
            elif path == "/api/import-local":
                count = self.store.import_local(payload.get("tasks", []), payload.get("activities", []))
                self.send_json(200, {"importedTasks": count, "status": "ok"})
            elif path == "/api/plans":
                if payload.get("useModel") is True:
                    model_status = get_model_status()
                    if not model_status.get("enabled"):
                        raise ValueError("Model requests are not enabled in local server settings.")
                    if model_status.get("remote") and payload.get("remoteConsent") is not True:
                        raise ValueError("Remote model requests require per-request consent.")
                    plan = self.store.save_plan(build_model_plan(payload.get("goal")))
                else:
                    plan = self.store.create_plan(payload.get("goal"))
                self.send_json(201, {"plan": plan})
            elif path == "/api/executions":
                execution = run_plan_execution(payload.get("planId"), self.store, self.workspace)
                self.send_json(201, {"execution": execution})
            else:
                self.send_json(404, {"error": "API route not found."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except ModelProviderError as exc:
            self.send_json(502, {"error": str(exc)})
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": "That task already exists."})
        except sqlite3.Error:
            self.send_json(500, {"error": "Local storage could not save the request."})

    def do_PATCH(self):
        if not self.safe_request():
            return
        match = re.fullmatch(r"/api/tasks/([^/]+)", urlparse(self.path).path)
        if not match:
            self.send_json(404, {"error": "API route not found."})
            return
        try:
            task = self.store.update_task(unquote(match.group(1)), self.read_json().get("status"))
            if task:
                self.send_json(200, {"task": task})
            else:
                self.send_json(404, {"error": "Task not found."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except sqlite3.Error:
            self.send_json(500, {"error": "Local storage could not update the task."})

    def do_DELETE(self):
        if not self.safe_request():
            return
        match = re.fullmatch(r"/api/tasks/([^/]+)", urlparse(self.path).path)
        if not match:
            self.send_json(404, {"error": "API route not found."})
            return
        try:
            if self.store.delete_task(unquote(match.group(1))):
                self.send_json(200, {"deleted": True})
            else:
                self.send_json(404, {"error": "Task not found."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except sqlite3.Error:
            self.send_json(500, {"error": "Local storage could not delete the task."})

    def serve_static(self, request_path):
        relative = "index.html" if request_path == "/" else unquote(request_path).lstrip("/")
        candidate = (ROOT / relative).resolve()
        if ROOT not in candidate.parents:
            self.send_json(403, {"error": "Path is not allowed."})
            return
        if not candidate.is_file():
            self.send_json(404, {"error": "File not found."})
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                        ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                        ".svg": "image/svg+xml"}.get(candidate.suffix.lower(), "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json(405, {"error": "Method not allowed."})


def main():
    Handler.store = Store(DB_PATH)
    Handler.workspace = Workspace()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"Nexora local server ready at http://{HOST}:{PORT}")
    print("SQLite persistence enabled. Plan previews are available; device execution remains disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Nexora local server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
