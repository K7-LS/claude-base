# -*- coding: utf-8 -*-
"""Провайдер-независимый разбор фактического usage из JSONL."""

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_usage_parser_deduplicates_requests_and_normalizes_three_shapes(tmp_path):
    from token_audit import audit_transcript

    transcript = tmp_path / "usage.jsonl"
    rows = [
        {
            "requestId": "claude-1",
            "usage": {
                "input_tokens": 20,
                "output_tokens": 5,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 7,
            },
        },
        {
            "requestId": "claude-1",
            "usage": {
                "input_tokens": 20,
                "output_tokens": 5,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 7,
            },
        },
        {
            "id": "openai-1",
            "response": {
                "usage": {
                    "input_tokens": 30,
                    "output_tokens": 8,
                    "input_tokens_details": {"cached_tokens": 11},
                }
            },
        },
        {
            "message": {
                "id": "opencode-1",
                "usage": {
                    "promptTokens": 40,
                    "completionTokens": 9,
                    "cachedTokens": 13,
                },
            }
        },
    ]
    _write_jsonl(transcript, rows)

    report = audit_transcript(transcript)

    assert report["requests"] == 3
    assert report["duplicates"] == 1
    assert report["totals"] == {
        "input_tokens": 90,
        "output_tokens": 22,
        "cache_read_tokens": 124,
        "cache_creation_tokens": 7,
        "processed_context_tokens": 197,
        "processed_total_tokens": 219,
    }
    assert report["per_request"]["processed_context_tokens"] == {
        "median": 40,
        "p95": 127,
        "max": 127,
    }
    assert report["max_processed_request"]["input_tokens"] == 20
    assert report["max_processed_request"]["processed_context_tokens"] == 127
    assert report["max_processed_request"]["request_fingerprint"]
    assert "claude-1" not in json.dumps(report)


def test_usage_parser_reports_malformed_lines_without_treating_them_as_usage(tmp_path):
    from token_audit import audit_transcript

    transcript = tmp_path / "usage.jsonl"
    transcript.write_text(
        '{"requestId":"ok","usage":{"input_tokens":2,"output_tokens":1}}\n'
        "{broken json\n"
        '{"event":"no usage"}\n',
        encoding="utf-8",
    )

    report = audit_transcript(transcript)

    assert report["requests"] == 1
    assert report["malformed_lines"] == 1
    assert report["ignored_records"] == 1


def test_usage_parser_never_returns_prompt_or_secret_payloads(tmp_path):
    from token_audit import audit_transcript

    transcript = tmp_path / "usage.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "requestId": "safe",
                "prompt": "SECRET_SENTINEL",
                "authorization": "Bearer SECRET_SENTINEL",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ],
    )

    serialized = json.dumps(audit_transcript(transcript), ensure_ascii=False)

    assert "SECRET_SENTINEL" not in serialized
    assert "authorization" not in serialized.lower()
