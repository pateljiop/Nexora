import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import server
from workspace_tools import Workspace
from planner import build_dry_run_plan, build_remote_plan


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = server.Store(Path(self.temp.name) / "test.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_create_trim_update_delete_and_activity(self):
        task = self.store.create_task("  Build locally  ", task_id="task-1")
        self.assertEqual(task["title"], "Build locally")
        self.assertEqual(self.store.update_task("task-1", "completed")["status"], "completed")
        self.assertTrue(self.store.delete_task("task-1"))
        self.assertFalse(self.store.delete_task("task-1"))
        self.assertEqual(len(self.store.list_activity()), 2)

    def test_rejects_invalid_titles_status_and_ids(self):
        for title in ("", "  ", "x" * 1201, None):
            with self.assertRaises(ValueError):
                self.store.create_task(title)
        with self.assertRaises(ValueError):
            self.store.create_task("valid", task_id="../unsafe")
        with self.assertRaises(ValueError):
            self.store.update_task("task-1", "running")

    def test_import_is_idempotent_and_does_not_overwrite_existing_task(self):
        original = self.store.create_task("Original", task_id="legacy-1")
        payload = [{"id": "legacy-1", "title": "Overwritten", "status": "completed",
                    "createdAt": original["createdAt"]},
                   {"id": "legacy-2", "title": "Imported", "status": "pending",
                    "createdAt": original["createdAt"]}]
        self.assertEqual(self.store.import_local(payload, []), 1)
        self.assertEqual(self.store.import_local(payload, []), 0)
        self.assertEqual({x["id"]: x["title"] for x in self.store.list_tasks()}["legacy-1"], "Original")

    def test_startup_recovery_marks_running_execution_failed(self):
        plan = build_remote_plan("Inspect", [
            {"title": "List", "detail": "Read only", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read", "detail": "Read only", "tool": "workspace.read", "arguments": {"path": "README.md"}},
            {"title": "Tasks", "detail": "Read only", "tool": "tasks.list", "arguments": {}}
        ])
        self.store.save_plan(plan)
        execution = self.store.start_execution(plan, plan["steps"])
        self.store.set_execution_step_status(execution["id"], plan["steps"][0]["id"], "running")
        self.assertEqual(self.store.recover_interrupted_executions(), 1)
        recovered = self.store.get_execution(execution["id"])
        self.assertEqual(recovered["status"], "failed")
        self.assertIn("Server restarted", recovered["verificationNote"])
        self.assertEqual(recovered["steps"][0]["status"], "failed")
        self.assertEqual(recovered["steps"][1]["status"], "skipped")

    def test_caps_activity(self):
        for i in range(40):
            self.store.add_activity(f"Event {i}")
        self.assertEqual(len(self.store.list_activity()), server.MAX_ACTIVITY)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        workspace_root = Path(self.temp.name) / "workspace"
        workspace_root.mkdir()
        (workspace_root / "sample.txt").write_text("workspace sample", encoding="utf-8")
        handler = type("TestHandler", (server.Handler,), {"store": server.Store(Path(self.temp.name) / "api.sqlite3"), "workspace": Workspace(workspace_root)})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urlopen(req, timeout=2) as response:
                raw = response.read().decode()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = raw
                return response.status, payload
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw
            return exc.code, payload

    def test_health_and_task_crud(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["storage"], "sqlite")
        self.assertEqual(health["execution"], "read_only_tools_only")
        status, created = self.request("/api/tasks", "POST", {"title": "Test task"})
        self.assertEqual(status, 201)
        task_id = created["task"]["id"]
        self.assertEqual(self.request(f"/api/tasks/{task_id}", "PATCH", {"status": "completed"})[1]["task"]["status"], "completed")
        self.assertEqual(self.request(f"/api/tasks/{task_id}", "DELETE")[0], 200)
        self.assertEqual(self.request("/api/tasks")[1]["tasks"], [])

    def test_plan_endpoint_persists_preview_without_execution(self):
        status, payload = self.request("/api/plans", "POST", {"goal": "Review my project"})
        self.assertEqual(status, 201)
        plan = payload["plan"]
        self.assertEqual(plan["mode"], "dry_run")
        self.assertFalse(plan["executionEnabled"])
        self.assertEqual(len(plan["steps"]), 4)
        self.assertEqual(self.request("/api/plans")[1]["plans"][0]["id"], plan["id"])
        self.assertIn("Plan preview created", [x["message"] for x in self.request("/api/activity")[1]["activities"]])

    def test_model_status_is_safe_and_remote_consent_is_required(self):
        status, model_status = self.request("/api/model/status")
        self.assertEqual(status, 200)
        self.assertNotIn("apiKey", model_status)
        with patch.dict("os.environ", {"NEXORA_MODEL_BASE_URL": "https://models.example/v1", "NEXORA_MODEL_API_KEY": "test-key", "NEXORA_MODEL_NAME": "test-model", "NEXORA_ALLOW_REMOTE_MODEL": "0"}):
            code, payload = self.request("/api/plans", "POST", {"goal": "Test", "useModel": True, "remoteConsent": True})
        self.assertEqual(code, 400)
        self.assertIn("not enabled", payload["error"])

    def test_read_only_workspace_api_and_traversal_protection(self):
        status, listing = self.request("/api/workspace")
        self.assertEqual(status, 200)
        self.assertIn("sample.txt", [item["path"] for item in listing["entries"]])
        status, preview = self.request("/api/workspace/read?path=sample.txt")
        self.assertEqual(status, 200)
        self.assertEqual(preview["content"], "workspace sample")
        self.assertTrue(preview["readOnly"])
        self.assertEqual(self.request("/api/workspace/read?path=..%2Foutside.txt")[0], 400)

    def test_execution_endpoint_runs_and_persists_read_only_steps(self):
        store = self.httpd.RequestHandlerClass.store
        plan = build_remote_plan("Inspect workspace", [
            {"title": "List files", "detail": "Read-only list.", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read sample", "detail": "Read-only preview.", "tool": "workspace.read", "arguments": {"path": "sample.txt"}},
            {"title": "List tasks", "detail": "Read-only tasks.", "tool": "tasks.list", "arguments": {}}
        ])
        store.save_plan(plan)
        status, payload = self.request("/api/executions", "POST", {"planId": plan["id"]})
        self.assertEqual(status, 202)
        execution = payload["execution"]
        import time
        for _ in range(60):
            latest = self.request(f"/api/executions/{execution['id']}")[1]["execution"]
            if latest["status"] != "running":
                execution = latest
                break
            time.sleep(0.05)
        self.assertEqual(execution["status"], "completed")
        self.assertFalse(execution["goalVerified"])
        self.assertEqual(len(execution["steps"]), 3)
        fetched = self.request(f"/api/executions/{execution['id']}")[1]["execution"]
        self.assertEqual(fetched["id"], execution["id"])
        history = self.request("/api/executions")[1]["executions"]
        self.assertTrue(any(item["id"] == execution["id"] for item in history))

    def test_execution_rejects_template_plan(self):
        store = self.httpd.RequestHandlerClass.store
        plan = build_dry_run_plan("Plan a day")
        store.save_plan(plan)
        status, payload = self.request("/api/executions", "POST", {"planId": plan["id"]})
        self.assertEqual(status, 400)
        self.assertIn("model-generated", payload["error"])

    def test_cancel_endpoint_sets_persistent_request(self):
        plan = build_remote_plan("Inspect", [
            {"title": "List", "detail": "Read only", "tool": "workspace.list", "arguments": {"path": "."}},
            {"title": "Read", "detail": "Read only", "tool": "workspace.read", "arguments": {"path": "sample.txt"}},
            {"title": "Tasks", "detail": "Read only", "tool": "tasks.list", "arguments": {}}
        ])
        self.httpd.RequestHandlerClass.store.save_plan(plan)
        execution = self.httpd.RequestHandlerClass.store.start_execution(plan, plan["steps"])
        status, payload = self.request(f"/api/executions/{execution['id']}/cancel", "POST", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["execution"]["cancelRequested"])
        self.assertTrue(self.httpd.RequestHandlerClass.store.is_execution_cancel_requested(execution["id"]))

    def test_static_server_only_exposes_browser_assets(self):
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/styles.css")[0], 200)
        self.assertEqual(self.request("/src/main.js")[0], 200)
        for path in ("/server.py", "/model_provider.py", "/DEVELOPMENT_LOG.md", "/.env", "/.env.example", "/data/state.sqlite3"):
            self.assertEqual(self.request(path)[0], 404, path)

    def test_rejects_invalid_payload_and_host(self):
        self.assertEqual(self.request("/api/tasks", "POST", {"title": " "})[0], 400)
        req = Request(self.base + "/api/health", headers={"Host": "attacker.example"})
        try:
            urlopen(req, timeout=2)
            self.fail("invalid Host should be rejected")
        except HTTPError as exc:
            self.assertEqual(exc.code, 403)

    def test_rejects_cross_origin(self):
        status, _ = self.request("/api/health", headers={"Origin": "https://attacker.example"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
