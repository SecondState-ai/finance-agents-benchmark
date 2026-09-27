from __future__ import annotations

import json
import tempfile
import unittest
from os import environ
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from harness.adapters.base import ModelResponse, ToolCall
from harness.adapters.openai import OpenAIAdapter
from harness.agent_loop import load_system_prompt, run_agent
from harness.tools import ToolExecutor, get_all_tool_definitions
from sandbox.sandbox import LocalSandbox

REPO_ROOT = Path(__file__).resolve().parent.parent


class HarnessTests(unittest.TestCase):
    def test_luna_uses_responses_api_with_same_default_inference_as_sol(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {
                "id": "resp-luna",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}],
                "usage": {"input_tokens": 2, "output_tokens": 1},
            }
        ).encode()
        context = MagicMock()
        context.__enter__.return_value = response
        with patch("harness.adapters.openai.urlopen", return_value=context) as mocked_urlopen:
            adapter = OpenAIAdapter("gpt-5.6-luna", api_key="not-a-real-key")
            adapter.complete([{"role": "user", "content": "hello"}], [])
        request = mocked_urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/responses"))
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        self.assertEqual(adapter.inference_parameters, {"api_mode": "responses", "reasoning_effort": "medium"})

    def test_sol_uses_responses_api_with_reasoning_and_preserves_tool_state(self) -> None:
        first_response = MagicMock()
        first_response.read.return_value = json.dumps(
            {
                "id": "resp-1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "read_json",
                        "arguments": '{"path":"input.json"}',
                    }
                ],
                "usage": {"input_tokens": 5, "output_tokens": 7},
            }
        ).encode()
        first_context = MagicMock()
        first_context.__enter__.return_value = first_response
        second_response = MagicMock()
        second_response.read.return_value = json.dumps(
            {
                "id": "resp-2",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}],
                "usage": {"input_tokens": 3, "output_tokens": 2},
            }
        ).encode()
        second_context = MagicMock()
        second_context.__enter__.return_value = second_response
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
        ]
        tools = [{"name": "read_json", "description": "Read JSON", "parameters": {"type": "object"}}]
        with patch("harness.adapters.openai.urlopen", side_effect=[first_context, second_context]) as mocked_urlopen:
            adapter = OpenAIAdapter("gpt-5.6-sol", api_key="not-a-real-key")
            first = adapter.complete(messages, tools)
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "read_json", "arguments": '{"path":"input.json"}'},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "call-1", "name": "read_json", "content": '{"ok":true}'},
                ]
            )
            second = adapter.complete(messages, tools)

        first_request = mocked_urlopen.call_args_list[0].args[0]
        first_body = json.loads(first_request.data)
        self.assertTrue(first_request.full_url.endswith("/responses"))
        self.assertEqual(first_body["instructions"], "system")
        self.assertEqual(first_body["input"], [{"role": "user", "content": "task"}])
        self.assertEqual(first_body["reasoning"], {"effort": "medium"})
        self.assertEqual(first_body["tools"], [{"type": "function", **tools[0]}])
        self.assertEqual(first.tool_calls[0], ToolCall("call-1", "read_json", '{"path":"input.json"}'))
        self.assertEqual(first.usage, {"input_tokens": 5, "output_tokens": 7})

        second_request = mocked_urlopen.call_args_list[1].args[0]
        second_body = json.loads(second_request.data)
        self.assertEqual(second_body["previous_response_id"], "resp-1")
        self.assertEqual(
            second_body["input"],
            [{"type": "function_call_output", "call_id": "call-1", "output": '{"ok":true}'}],
        )
        self.assertEqual(second.content, "done")
        self.assertEqual(adapter.inference_parameters, {"api_mode": "responses", "reasoning_effort": "medium"})

    def test_adapter_safely_loads_dotenv_without_executing_shell_and_prefers_exported_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env_file = root / ".env.local"
            marker = root / "must-not-exist"
            env_file.write_text(
                f"OPENAI_API_KEY=file-key\nUNRELATED=$(touch {marker})\n",
                encoding="utf-8",
            )
            with patch.dict(environ, {}, clear=True):
                from_file = OpenAIAdapter("gpt-5.6-luna", env_file=env_file)
            with patch.dict(environ, {"OPENAI_API_KEY": "exported-key"}, clear=True):
                exported = OpenAIAdapter("gpt-5.6-luna", env_file=env_file)
        self.assertEqual(from_file.api_key, "file-key")
        self.assertEqual(exported.api_key, "exported-key")
        self.assertFalse(marker.exists())

    def test_tools_enforce_dataset_and_output_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "a.json").write_text("[1,2]\n", encoding="utf-8")
            (dataset / "b.json").write_text("[3,4]\n", encoding="utf-8")
            (dataset / "secret.json").write_text("{}\n", encoding="utf-8")
            sandbox = LocalSandbox(
                dataset,
                root / "documents",
                root / "work",
                root / "output",
                ["a.json", "b.json"],
                ["answer.json"],
            )
            sandbox.start()
            executor = ToolExecutor(sandbox)
            read = json.loads(executor.execute("read", {"path": "/workspace/documents/a.json"}))
            self.assertEqual(json.loads(read["result"]["content"]), [1, 2])
            shell = json.loads(executor.execute("bash", {"command": "python -c 'print(2 + 3)'"}))
            self.assertEqual(shell["result"]["stdout"].strip(), "5")
            written = json.loads(executor.execute("write", {"path": "/workspace/output/answer.json", "content": '{"value": 1}\n'}))
            self.assertTrue(written["ok"])
            edited = json.loads(
                executor.execute(
                    "edit",
                    {"path": "/workspace/output/answer.json", "old_text": "1", "new_text": "2"},
                )
            )
            self.assertEqual(edited["result"]["replacements"], 1)
            matches = json.loads(executor.execute("glob", {"pattern": "/workspace/documents/*.json"}))
            self.assertEqual(len(matches["result"]["matches"]), 2)
            denied = json.loads(executor.execute("read", {"path": "/workspace/documents/secret.json"}))
            self.assertFalse(denied["ok"])
            traversal = json.loads(executor.execute("read", {"path": "/workspace/documents/../secret.json"}))
            self.assertFalse(traversal["ok"])
            immutable = json.loads(executor.execute("write", {"path": "/workspace/documents/a.json", "content": "[]\n"}))
            self.assertFalse(immutable["ok"])

    def test_public_tool_contract_is_generic_and_method_neutral(self) -> None:
        tools = get_all_tool_definitions()
        self.assertEqual({tool["name"] for tool in tools}, {"bash", "read", "write", "edit", "glob", "grep"})
        self.assertNotIn("query_json", {tool["name"] for tool in tools})
        prompt = (REPO_ROOT / "harness/system_prompt.md").read_text(encoding="utf-8")
        for value in ("/workspace/documents", "/workspace/work", "/workspace/output", "DuckDB", "pandas"):
            self.assertIn(value, prompt)

    def test_sandbox_image_pins_runtime_and_analysis_packages(self) -> None:
        dockerfile = (REPO_ROOT / "sandbox/Dockerfile").read_text(encoding="utf-8")
        requirements = (REPO_ROOT / "sandbox/requirements.lock").read_text(encoding="utf-8")
        from_lines = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
        self.assertEqual(len(from_lines), 1)
        self.assertRegex(from_lines[0], r"^FROM .+@sha256:[0-9a-f]{64}$", "base image must be content pinned")
        for requirement in ("duckdb==1.5.5", "duckdb-cli==1.5.5", "pandas==2.3.3"):
            self.assertIn(requirement, requirements)

    def test_system_prompt_describes_the_data_room_task(self) -> None:
        prompt = load_system_prompt(REPO_ROOT / "harness")
        for value in ("/workspace/documents", "/workspace/output/response.md", "index", "missing"):
            self.assertIn(value, prompt)

    def test_agent_loop_runs_tools_until_the_model_stops(self) -> None:
        class WritingAdapter:
            model_id = "unit-scripted"

            def __init__(self) -> None:
                self.turn = 0

            def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
                self.turn += 1
                if self.turn == 1:
                    arguments = json.dumps({"path": "/workspace/output/response.md", "content": "Revenue grew 20%.\n"})
                    return ModelResponse(None, [ToolCall("call-1", "write", arguments)], {"input_tokens": 10, "output_tokens": 5})
                return ModelResponse("Done.", [], {"input_tokens": 12, "output_tokens": 1})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "room").mkdir()
            (root / "room/index.csv").write_text("file\n", encoding="utf-8")
            sandbox = LocalSandbox(root / "room", root / "documents", root / "work", root / "output", ["index.csv"], ["response.md"])
            sandbox.start()
            metrics = run_agent(WritingAdapter(), "system", "question", ToolExecutor(sandbox), transcript_path=root / "transcript.jsonl")
            self.assertEqual((metrics["turns"], metrics["stop_reason"], metrics["tokens"]), (2, "model_stopped", {"input": 22, "output": 6}))
            self.assertEqual((root / "output/response.md").read_text(encoding="utf-8"), "Revenue grew 20%.\n")
            self.assertEqual(len((root / "transcript.jsonl").read_text(encoding="utf-8").splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
