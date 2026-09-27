"""Provider identity checks and temperature capability handling use no paid requests."""
import io
import json
import unittest
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from harness.adapters.openai import OpenAIAdapter


def reply(payload):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


class ProviderTests(unittest.TestCase):
    def test_describe_model_is_read_only(self):
        with patch("harness.adapters.openai.urlopen", return_value=reply({"id": "judge"})) as request:
            adapter = OpenAIAdapter("judge", api_key="fake")
            self.assertEqual(adapter.describe_model()["id"], "judge")
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_method(), "GET")
            self.assertTrue(sent.full_url.endswith("/models/judge"))

    def test_missing_model_is_not_substituted(self):
        with (patch("harness.adapters.openai.urlopen", side_effect=HTTPError("url", 404, "missing", Message(), io.BytesIO())),
              self.assertRaisesRegex(RuntimeError, "judge.*404")):
                OpenAIAdapter("judge", api_key="fake").describe_model()

    def test_temperature_zero_and_explicit_unsupported_rejection(self):
        rejection = HTTPError("url", 400, "unsupported", Message(), io.BytesIO(json.dumps({"error": {
            "param": "temperature", "code": "unsupported_parameter"}}).encode()))
        completed = {"id": "response", "output": [], "usage": {"input_tokens": 1, "output_tokens": 1}}
        with patch.object(OpenAIAdapter, "_temperature_unsupported", set()):
            with patch("harness.adapters.openai.urlopen", side_effect=[rejection, reply(completed)]) as request:
                adapter = OpenAIAdapter("judge", api_key="fake", temperature=0)
                adapter.complete([{"role": "user", "content": "test"}], [])
                self.assertEqual(json.loads(request.call_args_list[0].args[0].data)["temperature"], 0)
                self.assertNotIn("temperature", json.loads(request.call_args_list[1].args[0].data))
            with patch("harness.adapters.openai.urlopen", return_value=reply(completed)) as request:
                OpenAIAdapter("judge", api_key="fake", temperature=0).complete([{"role": "user", "content": "test"}], [])
                self.assertEqual(request.call_count, 1)
                self.assertNotIn("temperature", json.loads(request.call_args.args[0].data))

    def test_temperature_rejection_with_null_code(self):
        rejection = HTTPError("url", 400, "unsupported", Message(), io.BytesIO(json.dumps({"error": {
            "param": "temperature", "code": None,
            "message": "Unsupported parameter: 'temperature' is not supported with this model."}}).encode()))
        completed = {"id": "response", "output": [], "usage": {}}
        with (patch.object(OpenAIAdapter, "_temperature_unsupported", set()),
              patch("harness.adapters.openai.urlopen", side_effect=[rejection, reply(completed)]) as request):
            adapter = OpenAIAdapter("judge", api_key="fake", temperature=0)
            adapter.complete([], [])
            self.assertEqual(request.call_count, 2)
            self.assertTrue(adapter.inference_parameters["temperature_unsupported"])
            self.assertNotIn("temperature", json.loads(request.call_args.args[0].data))

    def test_strict_response_schema_is_sent_only_when_requested(self):
        from harness.judge import VERDICT_SCHEMA

        completed = {"id": "response", "output": [], "usage": {}}
        with patch("harness.adapters.openai.urlopen", return_value=reply(completed)) as request:
            OpenAIAdapter("judge", api_key="fake", response_schema=VERDICT_SCHEMA).complete([], [])
            self.assertEqual(json.loads(request.call_args.args[0].data)["text"]["format"],
                             {"type": "json_schema", "name": "response", "strict": True, "schema": VERDICT_SCHEMA})
            OpenAIAdapter("agent", api_key="fake").complete([], [])
            self.assertNotIn("text", json.loads(request.call_args.args[0].data))

    def test_configured_transport_timeout(self):
        with self.assertRaises(ValueError):
            OpenAIAdapter("judge", api_key="fake", timeout_seconds=0)
        with patch("harness.adapters.openai.urlopen", return_value=reply({"id": "response", "output": []})) as request:
            OpenAIAdapter("judge", api_key="fake", timeout_seconds=300).complete([], [])
            self.assertEqual(request.call_args.kwargs["timeout"], 300)

    def test_other_provider_errors_are_not_retried(self):
        with patch("harness.adapters.openai.urlopen", side_effect=HTTPError("url", 500, "error", Message(), io.BytesIO())) as request:
            with self.assertRaises(RuntimeError):
                OpenAIAdapter("judge", api_key="fake", temperature=0).complete([], [])
            self.assertEqual(request.call_count, 1)
