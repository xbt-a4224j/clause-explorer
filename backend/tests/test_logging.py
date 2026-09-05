"""Logging contract.

The Admin tab (#30) tails logs/explorer.jsonl and parses it into columns, which is why the
format is JSON lines rather than free text.

Redaction is a hard requirement, not a nicety: this repo is public and a key leaked into a
committed log or a pasted traceback is unrecoverable.

Test fixtures are ASSEMBLED AT RUNTIME rather than written as literals. A literal
credential-shaped string in a public repo trips secret scanners and push protection even
when it is obviously fake.
"""

from __future__ import annotations

import json

from explorer.api.logging import bind_request, configure_logging, get_logger, redact

# assembled, never a literal — see module docstring
FAKE_PROJ_KEY = "sk" + "-proj-" + "a" * 20
FAKE_BARE_KEY = "sk" + "-" + "b" * 24
FAKE_DSN = "postgresql://explorer:" + "hunter2" + "@db:5432/explorer"


class TestRedaction:
    def test_project_style_key_is_redacted(self) -> None:
        assert FAKE_PROJ_KEY not in redact(f"auth failed for {FAKE_PROJ_KEY}")

    def test_redaction_leaves_a_visible_marker(self) -> None:
        assert "***" in redact(f"token {FAKE_PROJ_KEY} rejected")

    def test_bare_key_is_redacted(self) -> None:
        assert FAKE_BARE_KEY not in redact(f"key={FAKE_BARE_KEY}")

    def test_dsn_password_is_redacted(self) -> None:
        out = redact(FAKE_DSN)
        assert "hunter2" not in out
        assert "***" in out

    def test_ordinary_text_is_untouched(self) -> None:
        msg = "retrieved 8 matters for industry=Healthcare"
        assert redact(msg) == msg


class TestStructuredOutput:
    def test_emits_valid_json_lines(self, capsys) -> None:
        configure_logging(level="INFO", to_file=False)
        get_logger("test").info("cube_query", measures=["deal_points.n"], row_count=8)
        line = capsys.readouterr().out.strip().splitlines()[-1]
        parsed = json.loads(line)  # must not raise
        assert parsed["event"] == "cube_query"
        assert parsed["row_count"] == 8

    def test_secret_in_a_log_value_is_redacted_in_output(self, capsys) -> None:
        configure_logging(level="INFO", to_file=False)
        get_logger("test").info("call_failed", detail=f"key {FAKE_PROJ_KEY} bad")
        out = capsys.readouterr().out
        assert FAKE_PROJ_KEY not in out
        assert "***" in out

    def test_request_id_binds_to_subsequent_logs(self, capsys) -> None:
        configure_logging(level="INFO", to_file=False)
        bind_request("req-abc")
        get_logger("test").info("nested_event")
        parsed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert parsed["request_id"] == "req-abc"


class TestRequestMiddleware:
    def test_every_response_carries_a_request_id_header(self) -> None:
        from explorer.api.main import app
        from fastapi.testclient import TestClient

        assert TestClient(app).get("/healthz").headers.get("x-request-id")
