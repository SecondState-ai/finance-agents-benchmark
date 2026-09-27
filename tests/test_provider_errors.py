"""Provider diagnostics retain useful categories without echoing request data."""
import json
import unittest

from harness.adapters.errors import ProviderRequestError


class ProviderErrorTests(unittest.TestCase):
    def test_context_rejection_is_classified_without_body(self):
        error = ProviderRequestError(400, json.dumps({'error': {
            'code': 'context_length_exceeded', 'message': 'Maximum context length exceeded. secret-prompt sk-secret'}}))
        self.assertEqual(error.details, {'http_status': 400, 'category': 'context_limit'})
        self.assertNotIn('secret', str(error))
        self.assertNotIn('secret', json.dumps(error.details))

    def test_tool_protocol_and_connection_related_codes(self):
        error = ProviderRequestError(400, json.dumps({'error': {'message': 'No tool output found for function call abc'}}))
        self.assertEqual(error.details['category'], 'tool_protocol')
        self.assertEqual(ProviderRequestError(429, '{}').details['category'], 'rate_limit')
        self.assertEqual(ProviderRequestError(503, '{}').details['category'], 'provider_unavailable')

    def test_malformed_or_unrecognized_details_are_not_retained(self):
        for body in ('private body', '[]', '{"error": "secret"}', '{"error":{"message":"secret"}}'):
            error = ProviderRequestError(400, body)
            self.assertEqual(error.details, {'http_status': 400, 'category': 'request_rejected'})
            self.assertNotIn('secret', str(error))
