"""Judge isolation, strict verdicts and aggregate scoring, with fake models only."""
import json
import unittest
from dataclasses import replace

from harness.adapters.base import ModelResponse
from harness.judge import JUDGE_MODEL, VERDICT_SCHEMA, JudgeResponseError, LLMJudge, Verdict, parse_verdict
from harness.runner import ROOT
from harness.scoring import grade_response, summarize
from harness.tasks import load_task


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.task = load_task(ROOT / "tasks/meridian/tasks/001/task.json")

    def test_one_fresh_call_per_criterion_and_payload_boundary(self):
        calls = []

        class Adapter:
            model_id = JUDGE_MODEL

            def complete(self, messages, tools):
                calls.append((messages, tools, self))
                return ModelResponse('{"verdict":"pass","reasoning":"Evidence satisfies this criterion."}', [],
                                     {"input_tokens": 5, "output_tokens": 3})

        score = grade_response(self.task, "Submitted answer", LLMJudge(Adapter))
        self.assertEqual(len(calls), len(self.task.criteria))
        self.assertIsNot(calls[0][2], calls[1][2])
        payload = json.loads(calls[0][0][1]["content"])
        self.assertEqual(set(payload), {"task_title", "task_instructions", "criterion", "response.md"})
        self.assertEqual(payload["task_instructions"], self.task.instructions)
        self.assertNotIn("facts", payload["criterion"])
        self.assertEqual(calls[0][1], [])
        self.assertTrue(score["all_pass"])
        self.assertEqual(score["tokens"]["input_tokens"], 10)

    def test_provider_judge_uses_approved_model_and_max_reasoning(self):
        from unittest.mock import patch

        from harness.scoring import provider_judge

        with patch("harness.scoring.OpenAIAdapter") as adapter:
            judge = provider_judge()
            adapter.return_value.describe_model.assert_called_once_with()
            judge.adapter_factory()
            self.assertEqual(adapter.call_count, 2)
            for call in adapter.call_args_list:
                self.assertEqual(call.args, ("gpt-6-luna",))
                self.assertEqual(call.kwargs["reasoning_effort"], "max")
                self.assertEqual(call.kwargs["temperature"], 0)
                self.assertEqual(call.kwargs["response_schema"], VERDICT_SCHEMA)
                self.assertEqual(call.kwargs["timeout_seconds"], 900)

    def test_invalid_paid_output_and_usage_are_retained(self):
        import tempfile
        from pathlib import Path

        class Adapter:
            model_id = JUDGE_MODEL

            def complete(self, messages, tools):
                return ModelResponse('invalid JSON', [], {"input_tokens": 17, "output_tokens": 9})

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "progress.json"
            for _ in range(2):
                with self.assertRaises(JudgeResponseError):
                    grade_response(self.task, "answer", LLMJudge(Adapter), checkpoint)
            records = [json.loads(line) for line in checkpoint.with_suffix(".failures.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["criterion_id"], "C-001")
            self.assertEqual(records[0]["response"]["usage"], {"input_tokens": 17, "output_tokens": 9})
            self.assertEqual(records[0]["response"]["content"], 'invalid JSON')
            self.assertFalse(checkpoint.exists())

    def test_malformed_verdicts_are_errors_not_passes(self):
        for value in (None, '{}', '```json\n{}\n```', '{"verdict":"maybe","reasoning":"x"}',
                      '{"verdict":"pass","reasoning":""}', '{"verdict":"pass","reasoning":"x","extra":true}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_verdict(value, {})

    def test_all_pass_and_weighted_tier_rate(self):
        class FakeJudge:
            model_id = "fake"
            policy_sha256 = "fake-policy-v1"

            def evaluate(self, task, criterion, response):
                return Verdict("fail" if criterion.id == "C-001" else "pass", "Intentional fake judgement")

        score = grade_response(self.task, "answer", FakeJudge())
        self.assertFalse(score["all_pass"])
        self.assertEqual(score["criterion_pass_rate"], .5)
        second = grade_response(replace(self.task, id="002", criteria=self.task.criteria[:1]), "answer", FakeJudge())
        summary = summarize([score, second])
        self.assertAlmostEqual(summary["easy"]["criterion_pass_rate"], 1/3)
        self.assertEqual(summary["easy"]["all_pass_rate"], 0)
        self.assertIsNone(summary["hard"]["criterion_pass_rate"])

    def test_checkpoint_resumes_without_repeating_paid_work(self):
        import tempfile
        from pathlib import Path

        class InterruptingJudge:
            model_id = "fake"
            policy_sha256 = "fake-policy-v1"

            def __init__(self):
                self.calls = []

            def evaluate(self, task, criterion, response):
                self.calls.append(criterion.id)
                if len(self.calls) == 2:
                    raise RuntimeError("interrupted")
                return Verdict("pass", "Satisfied", {"input_tokens": 2, "output_tokens": 1})

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "progress.json"
            first = InterruptingJudge()
            with self.assertRaises(RuntimeError):
                grade_response(self.task, "answer", first, checkpoint)
            second = InterruptingJudge()
            score = grade_response(self.task, "answer", second, checkpoint)
            self.assertEqual(second.calls, ["C-002"])
            self.assertEqual(score["tokens"]["input_tokens"], 4)
            with self.assertRaisesRegex(ValueError, "differs"):
                grade_response(self.task, "changed answer", second, checkpoint)
            for changed in (replace(self.task, instructions="Different request"),
                            replace(self.task, title="Different scope")):
                with self.assertRaisesRegex(ValueError, "differs"):
                    grade_response(changed, "answer", second, checkpoint)
            second.policy_sha256 = "changed-policy"
            with self.assertRaisesRegex(ValueError, "differs"):
                grade_response(self.task, "answer", second, checkpoint)
            self.assertEqual(second.calls, ["C-002"])

    def test_legacy_checkpoint_cannot_be_reused_under_new_policy(self):
        import tempfile
        from pathlib import Path

        class FakeJudge:
            model_id = "fake"
            policy_sha256 = "v2"

            def evaluate(self, task, criterion, response):
                return Verdict("pass", "Satisfied")

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "progress.json"
            grade_response(self.task, "answer", FakeJudge(), checkpoint)
            legacy = json.loads(checkpoint.read_text())
            del legacy["judge_policy_sha256"]
            checkpoint.write_text(json.dumps(legacy))
            with self.assertRaisesRegex(ValueError, "differs"):
                grade_response(self.task, "answer", FakeJudge(), checkpoint)

    def test_run_snapshot_and_score_artifact(self):
        import tempfile
        from pathlib import Path

        from test_runner import AnswerAdapter

        from harness.runner import run_task
        from harness.scoring import grade_run
        from sandbox.sandbox import LocalSandbox

        class FakeJudge:
            model_id = "fake"
            policy_sha256 = "fake-policy-v1"

            def evaluate(self, task, criterion, response):
                return Verdict("pass", "Satisfied", {"input_tokens": 1, "output_tokens": 1})

        with tempfile.TemporaryDirectory() as directory:
            run = run_task(self.task, AnswerAdapter(), Path(directory), sandbox_factory=LocalSandbox)
            score = grade_run(run, FakeJudge())
            self.assertEqual(json.loads((run / "scores.json").read_text()), score)
            with self.assertRaises(FileExistsError):
                grade_run(run, FakeJudge())
            (run / "scores.json").unlink()
            (run / "task.json").write_text('{}')
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                grade_run(run, FakeJudge())
