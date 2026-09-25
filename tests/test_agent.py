import json
import os
import unittest
from unittest.mock import patch

from pipe.analysis import agent
from pipe_api.dispatch import agent_route


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AgentTests(unittest.TestCase):
    def test_requires_server_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(agent.AgentUnavailable, "not configured"):
                agent.analyze(facts={"token": {"symbol": "PIPE"}}, question="read it")

    def test_returns_bounded_structured_analysis(self):
        structured = {
            "headline": "Authority state is the main verified signal",
            "answer": "The mint is readable and the supplied facts show no live authority.",
            "evidence": ["Mint authority is revoked."],
            "risks": ["Holder data is not available."],
            "unknowns": ["Creator behavior cannot be established."],
            "confidence": "medium",
        }
        provider = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(structured)}],
                }
            ]
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only", "OPENAI_MODEL": "gpt-6-astra"}, clear=True):
            with patch("pipe.analysis.agent.urlopen", return_value=_Response(provider)) as mocked:
                result = agent.analyze(
                    facts={"token": {"symbol": "PIPE", "mint_readable": True}},
                    question="What is verified?",
                )

        self.assertEqual(result["runtime"], "Fable 5.1")
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(result["evidence"], ["Mint authority is revoked."])
        request = mocked.call_args.args[0]
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent["model"], "gpt-6-astra")
        self.assertEqual(sent["reasoning"], {"effort": "medium"})
        self.assertNotIn("test-only", request.data.decode("utf-8"))

    def test_output_parser_ignores_non_message_items(self):
        payload = {
            "output": [
                {"type": "reasoning", "content": []},
                {"type": "message", "content": [{"type": "output_text", "text": "{\"ok\":true}"}]},
            ]
        }
        self.assertEqual(agent._output_text(payload), "{\"ok\":true}")

    def test_public_route_fails_closed_before_token_lookup_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            status, payload = agent_route(
                {
                    "mint": "So11111111111111111111111111111111111111112",
                    "question": "read it",
                },
                "127.0.0.1",
            )
        self.assertEqual(status, 503)
        self.assertFalse(payload["ok"])
        self.assertIn("not configured", payload["error"])


if __name__ == "__main__":
    unittest.main()
