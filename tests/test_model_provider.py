import json
import os
import unittest
from unittest.mock import patch

import model_provider
from model_provider import ModelProviderError, build_model_plan, get_model_status


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self.payload


def model_response(content):
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


class ModelProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "NEXORA_MODEL_BASE_URL": "https://models.example/v1",
            "NEXORA_MODEL_API_KEY": "test-secret-never-return",
            "NEXORA_MODEL_NAME": "test-model",
            "NEXORA_ALLOW_REMOTE_MODEL": "1"
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_status_never_exposes_api_key(self):
        status = get_model_status()
        self.assertTrue(status["configured"])
        self.assertTrue(status["enabled"])
        self.assertNotIn("test-secret-never-return", json.dumps(status))

    def test_remote_plan_is_validated_and_never_executable(self):
        steps = [{"title": f"Step {i}", "detail": "No action is performed in preview."} for i in range(1, 4)]
        with patch("model_provider.urlopen", return_value=FakeResponse(model_response({"steps": steps}))) as mocked:
            plan = build_model_plan("Plan a project")
        self.assertEqual(plan["source"], "remote_model")
        self.assertFalse(plan["executionEnabled"])
        self.assertTrue(all(step["sideEffects"] is False for step in plan["steps"]))
        request = mocked.call_args.args[0]
        authorization = request.get_header("Authorization") or request.headers.get("Authorization") or request.headers.get("authorization")
        self.assertEqual(authorization, "Bearer test-secret-never-return")

    def test_rejects_remote_http_endpoint_outside_loopback(self):
        with patch.dict(os.environ, {"NEXORA_MODEL_BASE_URL": "http://192.0.2.1/v1"}):
            with self.assertRaises(ModelProviderError):
                build_model_plan("Plan something")

    def test_local_endpoint_needs_no_api_key_or_remote_opt_in(self):
        local_steps = [{"title": f"Local step {i}", "detail": "Preview only."} for i in range(1, 4)]
        with patch.dict(os.environ, {
            "NEXORA_MODEL_BASE_URL": "http://127.0.0.1:11434/v1",
            "NEXORA_MODEL_API_KEY": "",
            "NEXORA_MODEL_NAME": "qwen2.5:3b",
            "NEXORA_ALLOW_REMOTE_MODEL": "0"
        }):
            status = get_model_status()
            self.assertTrue(status["enabled"])
            self.assertEqual(status["dataSharing"], "local_goal_stays_on_laptop")
            with patch("model_provider.urlopen", return_value=FakeResponse(model_response({"steps": local_steps}))) as mocked:
                plan = build_model_plan("Plan locally")
            self.assertEqual(plan["source"], "local_model")
            request = mocked.call_args.args[0]
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn("authorization", request.headers)

    def test_rejects_invalid_model_output(self):
        with patch("model_provider.urlopen", return_value=FakeResponse(model_response({"steps": [{"title": "Only one", "detail": ""}]}))):
            with self.assertRaises(ModelProviderError):
                build_model_plan("Plan something")

    def test_remote_planning_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {"NEXORA_MODEL_BASE_URL": "https://models.example/v1", "NEXORA_MODEL_API_KEY": "test-secret", "NEXORA_MODEL_NAME": "test-model", "NEXORA_ALLOW_REMOTE_MODEL": "0"}):
            self.assertFalse(get_model_status()["enabled"])
            with self.assertRaises(ModelProviderError):
                build_model_plan("Plan something")


if __name__ == "__main__":
    unittest.main()
