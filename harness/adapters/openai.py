"""Minimal OpenAI Responses API adapter for controlled model comparisons."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from harness.adapters.base import ModelResponse, ToolCall
from harness.adapters.errors import ProviderRequestError
from harness.dotenv import read_dotenv_value


class OpenAIAdapter:
    _temperature_unsupported: ClassVar[set[tuple[str, str]]] = set()

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
        env_file: Path | None = None,
        temperature: float | None = None,
        response_schema: dict[str, Any] | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self.model_id = model.removeprefix("openai/")
        file_api_key = read_dotenv_value(env_file, "OPENAI_API_KEY") if env_file else ""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or file_api_key
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_mode = "responses"
        self.temperature = temperature
        self.response_schema = response_schema
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        resolved_reasoning = reasoning_effort or "medium"
        self.inference_parameters: dict[str, Any] = {"api_mode": self.api_mode, "reasoning_effort": resolved_reasoning}
        if response_schema is not None:
            self.inference_parameters["response_format"] = "json_schema"
        if temperature is not None:
            self.inference_parameters["temperature"] = temperature
        self._previous_response_id: str | None = None
        self._message_count = 0
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required to run the harness")

    def describe_model(self) -> dict[str, Any]:
        """Read provider metadata without an inference request or token charge."""
        request = Request(f"{self.base_url}/models/{quote(self.model_id, safe='')}",
                          headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urlopen(request, timeout=30) as response:
                metadata = json.loads(response.read())
        except HTTPError as error:
            raise RuntimeError(f"Provider model lookup failed for {self.model_id} (HTTP {error.code})") from error
        if metadata.get("id") != self.model_id:
            raise RuntimeError(f"Provider did not confirm requested model id {self.model_id}")
        return metadata

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        return self._complete_responses(messages, tools)

    def _complete_responses(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        instructions = "\n\n".join(
            str(message["content"]) for message in messages if message["role"] == "system" and message.get("content")
        )
        if self._previous_response_id is None:
            response_input = [
                {"role": message["role"], "content": message["content"]} for message in messages if message["role"] != "system"
            ]
        else:
            response_input = [
                {
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": message["content"],
                }
                for message in messages[self._message_count :]
                if message["role"] == "tool"
            ]
        body: dict[str, Any] = {
            "model": self.model_id,
            "instructions": instructions,
            "input": response_input,
            "tools": [{"type": "function", **item} for item in tools],
            "tool_choice": "auto",
            "reasoning": {"effort": self.inference_parameters["reasoning_effort"]},
            "store": True,
        }
        if self.response_schema is not None:
            body["text"] = {"format": {"type": "json_schema", "name": "response",
                                       "strict": True, "schema": self.response_schema}}
        capability_key = (self.base_url, self.model_id)
        if self.temperature is not None and capability_key not in self._temperature_unsupported:
            body["temperature"] = self.temperature
        elif self.temperature is not None:
            self.inference_parameters["temperature"] = None
            self.inference_parameters["temperature_unsupported"] = True
        if self._previous_response_id is not None:
            body["previous_response_id"] = self._previous_response_id
        request = Request(
            f"{self.base_url}/responses",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            try:
                rejection = json.loads(detail).get("error", {})
            except json.JSONDecodeError:
                rejection = {}
            if (error.code == 400 and "temperature" in body and rejection.get("param") == "temperature"
                    and (rejection.get("code") in {"unsupported_parameter", "unsupported_value"}
                         or (rejection.get("code") is None and rejection.get("message") ==
                             "Unsupported parameter: 'temperature' is not supported with this model."))):
                # A rejected parameter request produced no model verdict. Cache the capability
                # and make exactly one successful inference for this criterion.
                self._temperature_unsupported.add(capability_key)
                return self._complete_responses(messages, tools)
            raise ProviderRequestError(error.code, detail) from error
        self._previous_response_id = payload["id"]
        self._message_count = len(messages)
        calls = [
            ToolCall(id=item["call_id"], name=item["name"], arguments=item["arguments"])
            for item in payload.get("output", [])
            if item.get("type") == "function_call"
        ]
        content_parts = [
            part["text"]
            for item in payload.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        usage = payload.get("usage") or {}
        return ModelResponse(
            content="\n".join(content_parts) or None,
            tool_calls=calls,
            usage={"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)},
        )
