"""Fireworks Chat Completions transport; credentials stay on the host."""
from __future__ import annotations

import json
import os
import time
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from harness.adapters.base import ModelResponse, ToolCall
from harness.adapters.errors import ProviderRequestError
from harness.dotenv import read_dotenv_value


class FireworksAdapter:
    def __init__(
        self, model: str, api_key: str | None = None, env_file: Path | None = None,
        base_url: str | None = None, reasoning_effort: str = "medium",
        max_tokens: int = 65536, timeout_seconds: float = 900,
    ) -> None:
        self.model_id = model
        if not model.startswith("accounts/fireworks/models/") or "/" in model.removeprefix("accounts/fireworks/models/"):
            raise ValueError("expected a Fireworks model resource name")
        file_key = read_dotenv_value(env_file, "FW_API_KEY") if env_file else None
        self.api_key = api_key or os.environ.get("FW_API_KEY") or file_key
        if not self.api_key:
            raise ValueError("FW_API_KEY is required to run Fireworks models")
        file_url = read_dotenv_value(env_file, "FW_BASE_URL") if env_file else None
        configured = base_url or os.environ.get("FW_BASE_URL") or file_url
        self.base_url = (configured or "https://api.fireworks.ai/inference/v1").rstrip("/").removesuffix("/chat/completions")
        if max_tokens < 1 or timeout_seconds <= 0:
            raise ValueError("token limit and timeout must be positive")
        self.timeout_seconds = timeout_seconds
        self.inference_parameters: dict[str, Any] = {
            "provider": "fireworks", "api_mode": "chat_completions", "base_url": self.base_url,
            "reasoning_effort": reasoning_effort, "max_tokens": max_tokens,
            "temperature": "provider_default", "reasoning_history": "provider_default",
            "context_length_exceeded_behavior": "error", "transport_retries": 0,
        }

    def describe_model(self) -> dict[str, Any]:
        request = Request(f"https://api.fireworks.ai/v1/{self.model_id}",
                          headers={"Authorization": f"Bearer {self.api_key}"})
        with urlopen(request, timeout=30) as response:
            metadata = json.loads(response.read())
        if metadata.get("name") != self.model_id or metadata.get("state") != "READY":
            raise ValueError("Fireworks did not confirm the requested model is ready")
        if not metadata.get("supportsServerless") or not metadata.get("supportsTools"):
            raise ValueError("Fireworks model must support serverless tool calls")
        return metadata

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self.model_id, "messages": messages, "stream": False,
            "reasoning_effort": self.inference_parameters["reasoning_effort"],
            "max_tokens": self.inference_parameters["max_tokens"],
            "context_length_exceeded_behavior": "error",
        }
        if tools:
            body.update(tools=[{"type": "function", "function": tool} for tool in tools], tool_choice="auto")
        request = Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode(), method="POST",
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read())
                break
            except HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                    # Do not expose provider bodies: they may echo prompt content or credentials.
                    detail = error.read().decode("utf-8", errors="replace")
                    raise ProviderRequestError(error.code, detail) from error
            except (URLError, IncompleteRead, RemoteDisconnected, TimeoutError, ConnectionError):
                if attempt == 2:
                    raise
            self.inference_parameters["transport_retries"] += 1
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError("Fireworks transport retries exhausted")
        choice = payload["choices"][0]
        message = choice["message"]
        usage = payload.get("usage") or {}
        tokens = {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)}
        for group, key, destination in [
            ("prompt_tokens_details", "cached_tokens", "cached_input_tokens"),
            ("completion_tokens_details", "reasoning_tokens", "reasoning_tokens"),
        ]:
            details = usage.get(group) or {}
            if key in details:
                tokens[destination] = details[key]
        return ModelResponse(
            content=message.get("content"),
            tool_calls=[ToolCall(call["id"], call["function"]["name"], call["function"]["arguments"])
                        for call in message.get("tool_calls") or []],
            usage=tokens, reasoning_content=message.get("reasoning_content"), finish_reason=choice.get("finish_reason"),
        )
