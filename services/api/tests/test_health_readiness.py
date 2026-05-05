"""Readiness endpoint tests."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_readyz_reports_schema_compatibility() -> None:
    from api.routers.health import readyz

    fake_app = SimpleNamespace(state=SimpleNamespace(db_pool=object()))

    with (
        patch.dict(sys.modules, {"api.app": SimpleNamespace(app=fake_app)}),
        patch(
            "api.routers.health.check_schema_compatibility",
            new=AsyncMock(
                return_value={
                    "compatible": True,
                    "required_states_missing": [],
                    "required_columns_missing": [],
                    "required_migrations_missing": [],
                    "constraint_present": True,
                    "errors": [],
                }
            ),
        ),
        patch(
            "api.routers.health.check_runtime_credentials",
            new=AsyncMock(
                return_value={
                    "enabled": False,
                    "status": "skipped",
                    "required_keys": ["AMP_API_KEY"],
                    "checked_keys": ["AMP_API_KEY"],
                    "probe_keys": [],
                    "missing_keys": [],
                    "invalid_keys": [],
                    "errors": [],
                    "provider_probe_errors": [],
                    "key_lengths": {},
                    "keys": {},
                }
            ),
        ),
    ):
        resp = await readyz()

    assert resp.status_code == 200
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["schema_compatibility"]["compatible"] is True
    assert payload["runtime_credentials"] == {
        "enabled": False,
        "status": "skipped",
        "missing_keys": False,
        "invalid_keys": False,
        "errors": False,
        "degraded": False,
    }


@pytest.mark.asyncio
async def test_readyz_returns_503_when_schema_incompatible() -> None:
    from api.routers.health import readyz

    fake_app = SimpleNamespace(state=SimpleNamespace(db_pool=object()))

    incompatible = {
        "compatible": False,
        "required_states_missing": ["suspended"],
        "required_columns_missing": [],
        "required_migrations_missing": [],
        "constraint_present": True,
        "errors": [],
    }

    with (
        patch.dict(sys.modules, {"api.app": SimpleNamespace(app=fake_app)}),
        patch(
            "api.routers.health.check_schema_compatibility",
            new=AsyncMock(return_value=incompatible),
        ),
        patch(
            "api.routers.health.check_runtime_credentials",
            new=AsyncMock(
                return_value={
                    "enabled": False,
                    "status": "skipped",
                    "required_keys": ["AMP_API_KEY"],
                    "checked_keys": ["AMP_API_KEY"],
                    "probe_keys": [],
                    "missing_keys": [],
                    "invalid_keys": [],
                    "errors": [],
                    "provider_probe_errors": [],
                    "key_lengths": {},
                    "keys": {},
                }
            ),
        ),
    ):
        resp = await readyz()

    assert resp.status_code == 503
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["status"] == "not_ready"
    assert payload["schema_compatibility"]["compatible"] is False


@pytest.mark.asyncio
async def test_readyz_returns_503_when_runtime_credentials_fail() -> None:
    from api.routers.health import readyz

    fake_app = SimpleNamespace(state=SimpleNamespace(db_pool=object()))
    schema_ok = {
        "compatible": True,
        "required_states_missing": [],
        "required_columns_missing": [],
        "required_migrations_missing": [],
        "constraint_present": True,
        "errors": [],
    }
    credentials_failed = {
        "enabled": True,
        "status": "failed",
        "required_keys": ["AMP_API_KEY"],
        "checked_keys": ["AMP_API_KEY"],
        "probe_keys": [],
        "missing_keys": ["AMP_API_KEY"],
        "invalid_keys": [],
        "errors": [],
        "provider_probe_errors": [],
        "key_lengths": {},
        "keys": {"AMP_API_KEY": {"status": "missing"}},
    }

    with (
        patch.dict(sys.modules, {"api.app": SimpleNamespace(app=fake_app)}),
        patch(
            "api.routers.health.check_schema_compatibility",
            new=AsyncMock(return_value=schema_ok),
        ),
        patch(
            "api.routers.health.check_runtime_credentials",
            new=AsyncMock(return_value=credentials_failed),
        ),
    ):
        resp = await readyz()

    assert resp.status_code == 503
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["status"] == "not_ready"
    assert payload["runtime_credentials"] == {
        "enabled": True,
        "status": "failed",
        "missing_keys": True,
        "invalid_keys": False,
        "errors": False,
        "degraded": False,
    }
    assert "AMP_API_KEY" not in json.dumps(payload["runtime_credentials"])
    assert "key_lengths" not in payload["runtime_credentials"]


@pytest.mark.asyncio
async def test_readyz_returns_200_when_runtime_credentials_degraded() -> None:
    from api.routers.health import readyz

    fake_app = SimpleNamespace(state=SimpleNamespace(db_pool=object()))
    schema_ok = {
        "compatible": True,
        "required_states_missing": [],
        "required_columns_missing": [],
        "required_migrations_missing": [],
        "constraint_present": True,
        "errors": [],
    }
    credentials_degraded = {
        "enabled": True,
        "status": "degraded",
        "required_keys": ["OPENAI_API_KEY"],
        "checked_keys": ["OPENAI_API_KEY"],
        "probe_keys": ["OPENAI_API_KEY"],
        "missing_keys": [],
        "invalid_keys": [],
        "errors": [],
        "provider_probe_errors": ["OPENAI_API_KEY:probe_request_failed:ConnectError"],
        "key_lengths": {"OPENAI_API_KEY": 20},
        "keys": {
            "OPENAI_API_KEY": {
                "status": "degraded",
                "provider": "openai",
                "error": "probe_request_failed:ConnectError",
            }
        },
    }

    with (
        patch.dict(sys.modules, {"api.app": SimpleNamespace(app=fake_app)}),
        patch(
            "api.routers.health.check_schema_compatibility",
            new=AsyncMock(return_value=schema_ok),
        ),
        patch(
            "api.routers.health.check_runtime_credentials",
            new=AsyncMock(return_value=credentials_degraded),
        ),
    ):
        resp = await readyz()

    assert resp.status_code == 200
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["runtime_credentials"] == {
        "enabled": True,
        "status": "degraded",
        "missing_keys": False,
        "invalid_keys": False,
        "errors": False,
        "degraded": True,
    }
    assert "OPENAI_API_KEY" not in json.dumps(payload["runtime_credentials"])
