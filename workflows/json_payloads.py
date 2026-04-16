from __future__ import annotations

import json
import re
from typing import Any, Iterable

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def extract_json_payload(
    text: str,
    *,
    preferred_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    if not text:
        return {
            "error": "agent response did not contain a JSON object",
            "raw_snippet": "",
        }

    candidates = _candidate_dicts(text)
    if not candidates:
        return {
            "error": "agent response did not contain a JSON object",
            "raw_snippet": text[:300],
        }

    preferred = {key for key in preferred_keys or [] if key}
    if preferred:
        exact_matches = [
            (index, payload)
            for index, payload in candidates
            if preferred.issubset(set(payload.keys()))
        ]
        if exact_matches:
            return sorted(exact_matches, key=lambda item: item[0])[0][1]

        partial_matches: list[tuple[int, int, int, dict[str, Any]]] = []
        for index, payload in candidates:
            overlap = len(preferred.intersection(set(payload.keys())))
            if overlap <= 0:
                continue
            extra_keys = len(set(payload.keys()) - preferred)
            partial_matches.append((overlap, extra_keys, index, payload))
        if partial_matches:
            best = sorted(partial_matches, key=lambda item: (-item[0], item[1], item[2]))[0]
            return best[3]

    return sorted(candidates, key=lambda item: item[0])[0][1]


def has_required_keys(payload: dict[str, Any], required_keys: Iterable[str]) -> bool:
    required = {key for key in required_keys if key}
    return required.issubset(set(payload.keys()))


def missing_required_keys(payload: dict[str, Any], required_keys: Iterable[str]) -> list[str]:
    payload_keys = set(payload.keys())
    return sorted(key for key in required_keys if key and key not in payload_keys)


def _candidate_dicts(text: str) -> list[tuple[int, dict[str, Any]]]:
    candidates: list[tuple[int, dict[str, Any]]] = []

    for match in _JSON_FENCE_RE.finditer(text):
        block = match.group(1).strip()
        if not block:
            continue
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.append((match.start(), payload))

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.append((index, payload))

    return candidates
