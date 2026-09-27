"""Safe provider failure categories; never persist echoed prompts or credentials."""
from __future__ import annotations

import json


class ProviderRequestError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        try:
            value = json.loads(body)
        except (ValueError, TypeError):
            value = {}
        rejection = value.get('error', {}) if isinstance(value, dict) else {}
        if not isinstance(rejection, dict):
            rejection = {}
        message = str(rejection.get('message', '')).lower()
        code = str(rejection.get('code', '')).lower()
        category = 'request_rejected'
        if status in (401, 403):
            category = 'access_denied'
        elif status == 402 or code == 'insufficient_quota':
            category = 'billing_or_quota'
        elif status == 429:
            category = 'rate_limit'
        elif status >= 500:
            category = 'provider_unavailable'
        elif code == 'context_length_exceeded' or any(phrase in message for phrase in (
                'maximum context length', 'context length exceeded', 'context window',
                'exceeds the context', 'exceed the context', 'too many tokens')):
            category = 'context_limit'
        elif any(phrase in message for phrase in ('tool_call_id', 'function_call_output',
                                                  'no tool output found', 'function call output')):
            category = 'tool_protocol'
        self.details = {'http_status': status, 'category': category}
        super().__init__(f'Provider request failed (HTTP {status}; {category})')
