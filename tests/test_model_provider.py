import io
import json
import os
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

import model_provider
from model_provider import ModelProviderError, analyze_screen_frame, build_model_plan, get_model_status


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

    def test_provider_request_opener_installs_no_redirect_handler(self):
        sentinel = object()
        opener = MagicMock()
        opener.open.return_value = sentinel
        with patch("model_provider.build_opener", return_value=opener) as build_opener:
            self.assertIs(model_provider._open_provider_request(
                model_provider.Request("https://models.example/v1/chat/completions")
            ), sentinel)
        opener.open.assert_called_once()
        build_opener.assert_called_once()
        handlers = build_opener.call_args.args
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], model_provider._NoRedirectHandler)

    def test_provider_redirects_are_disabled(self):
        handler = model_provider._NoRedirectHandler()
        request = model_provider.Request("https://models.example/v1/chat/completions")
        self.assertIsNone(handler.redirect_request(
            request, None, 302, "Found", {}, "https://unexpected.example/collect"
        ))

    def test_provider_connection_errors_are_generic(self):
        failures = (
            URLError("connection failed with test-secret-never-return"),
            TimeoutError("timed out for test-secret-never-return"),
            OSError("socket failure: test-secret-never-return"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with patch("model_provider._open_provider_request", side_effect=failure):
                    with self.assertRaises(ModelProviderError) as raised:
                        build_model_plan("Summarize the workspace")
                self.assertEqual(
                    str(raised.exception),
                    "Could not reach the configured model provider before timeout.",
                )
                self.assertNotIn("test-secret-never-return", str(raised.exception))

    def test_provider_http_error_does_not_expose_response_body_or_api_key(self):
        error = HTTPError(
            "https://models.example/v1/chat/completions",
            502,
            "Bad Gateway",
            {},
            io.BytesIO(b"upstream echoed test-secret-never-return"),
        )
        with patch("model_provider._open_provider_request", side_effect=error):
            with self.assertRaises(ModelProviderError) as raised:
                build_model_plan("Summarize the workspace")
        self.assertEqual(str(raised.exception), "Model provider returned HTTP 502.")
        self.assertNotIn("test-secret-never-return", str(raised.exception))
        self.assertNotIn("upstream echoed", str(raised.exception))

    def test_status_never_exposes_api_key(self):
        status = get_model_status()
        self.assertTrue(status["configured"])
        self.assertTrue(status["enabled"])
        self.assertNotIn("test-secret-never-return", json.dumps(status))

    def test_remote_plan_is_validated_and_never_executable(self):
        steps = [{"title": f"Step {i}", "detail": "No action is performed in preview."} for i in range(1, 4)]
        with patch("model_provider._open_provider_request", return_value=FakeResponse(model_response({"steps": steps}))) as mocked:
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
            with patch("model_provider._open_provider_request", return_value=FakeResponse(model_response({"steps": local_steps}))) as mocked:
                plan = build_model_plan("Plan locally")
            self.assertEqual(plan["source"], "local_model")
            request = mocked.call_args.args[0]
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn("authorization", request.headers)

    def test_rejects_invalid_model_output(self):
        with patch("model_provider._open_provider_request", return_value=FakeResponse(model_response({"steps": [{"title": "Only one", "detail": ""}]}))):
            with self.assertRaises(ModelProviderError):
                build_model_plan("Plan something")

    def test_screen_analysis_sends_only_valid_bounded_jpeg_and_returns_text(self):
        image = "data:image/jpeg;base64," + __import__("base64").b64encode(bytes([255, 216, 255]) + b"sample").decode("ascii")
        with patch("model_provider._open_provider_request", return_value=FakeResponse({"choices": [{"message": {"content": "A settings window is visible."}}]})) as mocked:
            result = analyze_screen_frame(image, "Explain the visible error")
        self.assertEqual(result, "A settings window is visible.")
        request = mocked.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        user_content = payload["messages"][1]["content"]
        self.assertEqual(user_content[0]["text"], "Explain the visible error")
        self.assertEqual(user_content[1]["image_url"]["url"], image)
        self.assertNotIn("test-secret-never-return", json.dumps(payload))

    def test_screen_analysis_rejects_invalid_jpeg_and_oversized_question(self):
        with self.assertRaises(ModelProviderError):
            analyze_screen_frame("data:image/png;base64,AAAA", "Describe")
        image = "data:image/jpeg;base64," + __import__("base64").b64encode(bytes([255, 216, 255]) + b"sample").decode("ascii")
        with self.assertRaises(ModelProviderError):
            analyze_screen_frame(image, "q" * 1001)

    def test_remote_planning_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {"NEXORA_MODEL_BASE_URL": "https://models.example/v1", "NEXORA_MODEL_API_KEY": "test-secret", "NEXORA_MODEL_NAME": "test-model", "NEXORA_ALLOW_REMOTE_MODEL": "0"}):
            self.assertFalse(get_model_status()["enabled"])
            with self.assertRaises(ModelProviderError):
                build_model_plan("Plan something")


if __name__ == "__main__":
    unittest.main()
