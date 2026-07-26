# -*- coding: utf-8 -*-
"""Безопасная агрегация usage из JSONL без возврата содержимого запросов."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterator


def _dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _dicts(child)


def _usage_dict(record: dict[str, Any]) -> dict[str, Any] | None:
    for candidate in _dicts(record):
        usage = candidate.get("usage")
        if isinstance(usage, dict):
            return usage
    return None


def _first_int(data: dict[str, Any], names: tuple[str, ...]) -> int:
    for name in names:
        value = data.get(name)
        if isinstance(value, int) and value >= 0:
            return value
    return 0


def _normalize_usage(usage: dict[str, Any]) -> dict[str, int | bool]:
    details = usage.get("input_tokens_details")
    details = details if isinstance(details, dict) else {}
    cache_included_in_input = False
    cached = _first_int(
        usage,
        (
            "cache_read_input_tokens",
        ),
    )
    if not cached:
        cached = _first_int(usage, ("cached_tokens", "cachedTokens"))
        cache_included_in_input = cached > 0
    if not cached:
        cached = _first_int(details, ("cached_tokens", "cachedTokens"))
        cache_included_in_input = cached > 0
    normalized: dict[str, int | bool] = {
        "input_tokens": _first_int(usage, ("input_tokens", "prompt_tokens", "promptTokens")),
        "output_tokens": _first_int(
            usage, ("output_tokens", "completion_tokens", "completionTokens")
        ),
        "cache_read_tokens": cached,
        "cache_creation_tokens": _first_int(
            usage,
            (
                "cache_creation_input_tokens",
                "cache_creation_tokens",
                "cacheCreationTokens",
            ),
        ),
        "_cache_included_in_input": cache_included_in_input,
    }
    normalized["processed_context_tokens"] = (
        int(normalized["input_tokens"])
        + int(normalized["cache_creation_tokens"])
        + (0 if cache_included_in_input else int(normalized["cache_read_tokens"]))
    )
    normalized["processed_total_tokens"] = (
        int(normalized["processed_context_tokens"]) + int(normalized["output_tokens"])
    )
    return normalized


def _request_id(record: dict[str, Any], line_number: int) -> str:
    for name in ("requestId", "request_id"):
        value = record.get(name)
        if isinstance(value, str) and value:
            return value
    for holder in (record, record.get("response"), record.get("message")):
        if isinstance(holder, dict):
            value = holder.get("id")
            if isinstance(value, str) and value:
                return value
    return f"line:{line_number}"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _distribution(values: list[int]) -> dict[str, int]:
    if not values:
        return {"median": 0, "p95": 0, "max": 0}
    ordered = sorted(values)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "median": int(statistics.median(ordered)),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def audit_transcript(path: Path) -> dict[str, Any]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "processed_context_tokens": 0,
        "processed_total_tokens": 0,
    }
    seen: set[str] = set()
    duplicates = 0
    malformed = 0
    ignored = 0
    samples = {key: [] for key in totals}
    maximum = {**totals, "request_fingerprint": None}

    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(record, dict):
                ignored += 1
                continue
            usage = _usage_dict(record)
            if usage is None:
                ignored += 1
                continue
            request_id = _request_id(record, line_number)
            if request_id in seen:
                duplicates += 1
                continue
            seen.add(request_id)
            normalized = _normalize_usage(usage)
            for key in totals:
                value = int(normalized[key])
                totals[key] += value
                samples[key].append(value)
            if normalized["processed_context_tokens"] > maximum["processed_context_tokens"]:
                maximum = {
                    **{key: int(normalized[key]) for key in totals},
                    "request_fingerprint": _fingerprint(request_id),
                }

    return {
        "file": path.name,
        "requests": len(seen),
        "duplicates": duplicates,
        "malformed_lines": malformed,
        "ignored_records": ignored,
        "totals": totals,
        "per_request": {key: _distribution(values) for key, values in samples.items()},
        "max_processed_request": maximum,
    }
