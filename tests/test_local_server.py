import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


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

    def test_caps_activity(self):
        for i in range(40):
            self.store.add_activity(f"Event {i}")
        self.assertEqual(len(self.store.list_activity()), server.MAX_ACTIVITY)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        handler = type("TestHandler", (server.Handler,), {"store": server.Store(Path(self.temp.name) / "api.sqlite3")})
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
                return response.status, json.loads(response.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_health_and_task_crud(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["storage"], "sqlite")
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
        self.assertIn("Dry-run plan preview created", [x["message"] for x in self.request("/api/activity")[1]["activities"]])

    def test_model_status_is_safe_and_remote_consent_is_required(self):
        status, model_status = self.request("/api/model/status")
        self.assertEqual(status, 200)
        self.assertNotIn("apiKey", model_status)
        with patch.dict("os.environ", {"NEXORA_ALLOW_REMOTE_MODEL": "0"}):
            code, payload = self.request("/api/plans", "POST", {"goal": "Test", "remoteConsent": True})
        self.assertEqual(code, 400)
        self.assertIn("not enabled", payload["error"])

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
