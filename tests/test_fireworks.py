"""Fireworks wire format, credential boundaries and multi-turn reasoning without paid calls."""
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from harness.adapters.fireworks import FireworksAdapter
from harness.agent_loop import run_agent
from harness.tools import ToolExecutor
from sandbox.sandbox import LocalSandbox
from tests.test_provider import reply

MODEL = "accounts/fireworks/models/deepseek-v4p1-flash"


def completion(message, finish="stop"):
    return reply({"choices": [{"message": message, "finish_reason": finish}],
                  "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                            "prompt_tokens_details": {"cached_tokens": 3},
                            "completion_tokens_details": {"reasoning_tokens": 2}}})


class FireworksTests(unittest.TestCase):
    def test_key_and_full_endpoint_from_dotenv(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            env = Path(directory) / ".env.local"
            env.write_text('FW_API_KEY="test-secret"\nFW_BASE_URL="https://api.fireworks.ai/inference/v1/chat/completions"\n')
            adapter = FireworksAdapter(MODEL, env_file=env)
            self.assertEqual(adapter.api_key, "test-secret")
            self.assertEqual(adapter.base_url, "https://api.fireworks.ai/inference/v1")
            self.assertNotIn("test-secret", json.dumps(adapter.inference_parameters))
            with self.assertRaisesRegex(ValueError, "FW_API_KEY"):
                FireworksAdapter(MODEL)

    def test_model_lookup_requires_exact_ready_tool_model(self):
        metadata = {"name": MODEL, "state": "READY", "supportsServerless": True, "supportsTools": True}
        with patch("harness.adapters.fireworks.urlopen", return_value=reply(metadata)) as request:
            self.assertEqual(FireworksAdapter(MODEL, api_key="fake").describe_model(), metadata)
            self.assertEqual(request.call_args.args[0].get_method(), "GET")
        with (patch("harness.adapters.fireworks.urlopen", return_value=reply({**metadata, "supportsTools": False})),
              self.assertRaises(ValueError)):
            FireworksAdapter(MODEL, api_key="fake").describe_model()

    def test_loop_replays_reasoning_and_tools_and_retains_usage(self):
        call = {"id": "write-1", "type": "function", "function": {"name": "write", "arguments": json.dumps({
            "path": "/workspace/output/response.md", "content": "Answer"})}}
        responses = [completion({"content": None, "reasoning_content": "Inspect the evidence.", "tool_calls": [call]}, "tool_calls"),
                     completion({"content": "Done"})]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sandbox = LocalSandbox(dataset_root=root, documents_dir=root / "docs", work_dir=root / "work", output_dir=root / "out",
                                   allowed_dataset_files=[], allowed_output_files=["response.md"])
            sandbox.start()
            try:
                with patch("harness.adapters.fireworks.urlopen", side_effect=responses) as request:
                    metrics = run_agent(FireworksAdapter(MODEL, api_key="fake"), "system", "request", ToolExecutor(sandbox),
                                        transcript_path=root / "transcript.jsonl")
                first, second = [json.loads(c.args[0].data) for c in request.call_args_list]
                self.assertEqual(first["tools"][0]["type"], "function")
                self.assertIn("parameters", first["tools"][0]["function"])
                self.assertNotIn("previous_response_id", second)
                self.assertNotIn("temperature", first)
                self.assertEqual(second["messages"][2]["reasoning_content"], "Inspect the evidence.")
                self.assertEqual(second["messages"][2]["tool_calls"], [call])
                self.assertEqual(second["messages"][3]["tool_call_id"], "write-1")
                self.assertEqual(metrics["tokens"], {"input": 20, "output": 10})
                events = [json.loads(line) for line in (root / "transcript.jsonl").read_text().splitlines()]
                self.assertEqual(events[0]["usage"]["cached_input_tokens"], 3)
                self.assertEqual(events[0]["usage"]["reasoning_tokens"], 2)
                self.assertEqual(events[0]["finish_reason"], "tool_calls")
            finally:
                sandbox.stop()

    def test_truncated_tool_call_is_recorded_but_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = ToolExecutor(LocalSandbox(dataset_root=root, documents_dir=root / "docs", work_dir=root / "work",
                                                 output_dir=root / "out", allowed_dataset_files=[], allowed_output_files=[]))
            with patch("harness.adapters.fireworks.urlopen", return_value=completion({"content": "partial"}, "length")):
                metrics = run_agent(FireworksAdapter(MODEL, api_key="fake"), "system", "request", executor)
            self.assertEqual(metrics["stop_reason"], "provider_length")
            self.assertEqual(metrics["tokens"], {"input": 10, "output": 5})
            self.assertEqual(executor.events, [])

    def test_transient_failure_retries_same_body_but_auth_does_not(self):
        error = HTTPError("url", 429, "busy", Message(), io.BytesIO())
        with (patch("harness.adapters.fireworks.urlopen", side_effect=[error, completion({"content": "Done"})]) as request,
              patch("harness.adapters.fireworks.time.sleep")):
            adapter = FireworksAdapter(MODEL, api_key="fake")
            adapter.complete([{"role": "user", "content": "request"}], [])
            self.assertEqual(request.call_args_list[0].args[0].data, request.call_args_list[1].args[0].data)
            self.assertEqual(adapter.inference_parameters["transport_retries"], 1)
        secret_error = HTTPError("url", 401, "unauthorized", Message(), io.BytesIO(b"secret-body"))
        with patch("harness.adapters.fireworks.urlopen", side_effect=secret_error) as request:
            with self.assertRaisesRegex(RuntimeError, r"^Provider request failed \(HTTP 401; access_denied\)$"):
                FireworksAdapter(MODEL, api_key="fake").complete([], [])
            self.assertEqual(request.call_count, 1)
