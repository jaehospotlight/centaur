from __future__ import annotations


def test_handler_discovery_respects_workflow_allowlist(monkeypatch, tmp_path):
    from api.workflow_engine import discover_workflow_handlers, get_workflow_handler

    overlay_workflow = tmp_path / "sample_overlay_digest.py"
    overlay_workflow.write_text(
        "WORKFLOW_NAME = 'sample_overlay_digest'\n"
        "PROMPT = 'Generate the sample overlay digest.'\n"
    )
    monkeypatch.setenv("WORKFLOW_DIRS", str(tmp_path))
    monkeypatch.setenv("CENTAUR_ENABLED_WORKFLOWS", "agent_turn,slack_thread_turn")

    discovered = discover_workflow_handlers()
    assert "agent_turn" in discovered
    assert "slack_thread_turn" in discovered
    assert "sample_overlay_digest" not in discovered
    assert get_workflow_handler("sample_overlay_digest") is None
