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
from urllib.parse import unquote, urlparse

from planner import build_dry_run_plan, validate_plan

ROOT = Path(__file__).resolve().parent
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
        if status not in STATUSES:
            raise ValueError("Unsupported task status.")
        with self.connect() as db:
            cursor = db.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, now_iso(), task_id))
            row = db.execute("SELECT id,title,status,created_at,updated_at FROM tasks WHERE id=?", (task_id,)).fetchone()
        if cursor.rowcount:
            self.add_activity("Task marked complete" if status == "completed" else "Task reopened", row["title"])
        return self.task_dict(row) if row else None

    def delete_task(self, task_id):
        if not ID_PATTERN.fullmatch(task_id):
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


    def create_plan(self, goal):
        plan = validate_plan(build_dry_run_plan(goal))
        with self.connect() as db:
            db.execute("INSERT INTO plans(id,goal,payload_json,created_at) VALUES(?,?,?,?)",
                       (plan["id"], plan["goal"], json.dumps(plan, ensure_ascii=False), plan["createdAt"]))
            db.execute("DELETE FROM plans WHERE id NOT IN (SELECT id FROM plans ORDER BY created_at DESC LIMIT 200)")
        self.add_activity("Dry-run plan preview created", plan["goal"])
        return plan

    def list_plans(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload_json FROM plans ORDER BY created_at DESC LIMIT 50").fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

class Handler(BaseHTTPRequestHandler):
    server_version = "NexoraLocal/1.0"
    store = None

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
                plan = self.store.create_plan(payload.get("goal"))
                self.send_json(201, {"plan": plan})
            else:
                self.send_json(404, {"error": "API route not found."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
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
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"Nexora local server ready at http://{HOST}:{PORT}")
    print("SQLite persistence enabled. AI planning and device execution remain disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Nexora local server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
