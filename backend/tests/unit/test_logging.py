"""Redaction processor contract: pure, recursive, non-mutating, JSON-safe."""

import copy
import json

from app.logging_setup import REDACTED, redact_processor

SENSITIVE_KEYS = [
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "content",
    "answer",
    "prompt",
]


def run(event_dict: dict) -> dict:
    # structlog processor signature: (logger, method_name, event_dict).
    return redact_processor(None, "info", event_dict)


class TestTopLevelRedaction:
    def test_every_sensitive_key_is_redacted(self):
        event = {key: f"value-{key}" for key in SENSITIVE_KEYS}
        redacted = run(event)
        for key in SENSITIVE_KEYS:
            assert redacted[key] == REDACTED

    def test_matching_is_case_insensitive_and_substring(self):
        event = {
            "PASSWORD": "hunter2",
            "Authorization": "Bearer abc123",
            "refresh_token": "rt-1",
            "JWT_SECRET": "s3cret",
            "Set-Cookie": "bv_refresh=xyz",
            "user_prompt": "my startup pitch",
            "modelAnswer": "verdict text",
        }
        redacted = run(event)
        assert all(value == REDACTED for value in redacted.values())


class TestRecursion:
    def test_nested_dicts_and_lists_are_redacted(self):
        event = {
            "event": "analysis.completed",
            "request": {
                "headers": {"authorization": "Bearer real-token", "accept": "application/json"},
                "body": {"answers": [{"content": "founder text", "step": 3}]},
            },
            "attempts": [
                {"token": "t-1", "status": 500},
                {"token": "t-2", "status": 200},
            ],
        }
        redacted = run(event)
        assert redacted["request"]["headers"]["authorization"] == REDACTED
        assert redacted["request"]["headers"]["accept"] == "application/json"
        assert redacted["request"]["body"]["answers"] == REDACTED
        assert redacted["attempts"][0] == {"token": REDACTED, "status": 500}
        assert redacted["attempts"][1] == {"token": REDACTED, "status": 200}

    def test_sensitive_key_with_container_value_is_fully_masked(self):
        event = {"secrets": {"jwt": "a", "openai": "b"}, "prompt_parts": ["p1", "p2"]}
        redacted = run(event)
        assert redacted["secrets"] == REDACTED
        assert redacted["prompt_parts"] == REDACTED


class TestPurity:
    def test_input_event_dict_is_not_mutated(self):
        event = {
            "password": "hunter2",
            "nested": {"token": "t-1", "items": [{"secret": "s"}]},
        }
        snapshot = copy.deepcopy(event)
        run(event)
        assert event == snapshot

    def test_harmless_metadata_preserved(self):
        event = {
            "event": "request.completed",
            "method": "GET",
            "path": "/healthz",
            "status": 200,
            "duration_ms": 12.5,
            "request_id": "abc123",
            "user_id": "9b2e7a1c",
        }
        assert run(event) == event


class TestSerializedOutput:
    def test_no_sensitive_value_survives_json_serialization(self):
        sensitive_values = [
            "hunter2-password-value",
            "Bearer eyJhbGciOiJIUzI1NiJ9",
            "sk-proj-abcdef1234567890",
            "full founder answer body",
        ]
        event = {
            "password": sensitive_values[0],
            "headers": {"authorization": sensitive_values[1]},
            "config": [{"openai_secret": sensitive_values[2]}],
            "submission": {"answer": sensitive_values[3]},
            "event": "kept",
        }
        serialized = json.dumps(run(event))
        for value in sensitive_values:
            assert value not in serialized
        assert "kept" in serialized
