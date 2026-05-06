from __future__ import annotations

from scripts.build_self_improve_notifier_input import build_notifier_input


def _ancestor(commit: str, after: str) -> bool:
    return commit in {"merge-a", after}


def test_build_notifier_input_keeps_label_only_prs_without_notifications() -> None:
    payload = build_notifier_input(
        [
            {
                "number": 624,
                "url": "https://github.com/paradigmxyz/centaur/pull/624",
                "title": "Add market move mode",
                "body": "Concise summary only.",
                "mergeCommit": {"oid": "merge-a"},
            }
        ],
        before_sha="before",
        after_sha="after",
        baseline_sha="",
        repo="paradigmxyz/centaur",
        deployed_at="2026-05-06T00:00:00Z",
        commit_is_ancestor=_ancestor,
    )

    assert payload["merged_prs"] == [
        {
            "pr_number": 624,
            "pr_url": "https://github.com/paradigmxyz/centaur/pull/624",
            "summary": "Add market move mode",
        }
    ]
    assert payload["notifications"] == []


def test_build_notifier_input_still_uses_optional_metadata_for_notifications() -> None:
    body = (
        "Summary.\n"
        "<!-- self_improve_metadata_v1:start -->\n"
        '{"summary":"Live fix","source_threads":[{"thread_key":"C123:1700.1"}]}\n'
        "<!-- self_improve_metadata_v1:end -->"
    )
    payload = build_notifier_input(
        [
            {
                "number": 625,
                "url": "https://github.com/paradigmxyz/centaur/pull/625",
                "title": "Fallback title",
                "body": body,
                "mergeCommit": {"oid": "merge-a"},
            }
        ],
        before_sha="before",
        after_sha="after",
        baseline_sha="",
        repo="paradigmxyz/centaur",
        deployed_at="2026-05-06T00:00:00Z",
        commit_is_ancestor=_ancestor,
    )

    assert payload["merged_prs"][0]["summary"] == "Live fix"
    assert payload["notifications"][0]["channel"] == "C123"
