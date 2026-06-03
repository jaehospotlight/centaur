from __future__ import annotations

import base64
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from api.integrations import gmail_oauth
from api.routers import gmail_oauth as gmail_router


@pytest.fixture(autouse=True)
def gmail_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_OAUTH_STATE_SIGNING_KEY", "state-secret")
    monkeypatch.setenv(
        "GMAIL_OAUTH_TOKEN_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="),
    )
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_OAUTH_REDIRECT_URI", "https://centaur.example/gmail-oauth/callback")


def test_pairing_code_required_for_oauth_url() -> None:
    code, token = gmail_oauth.build_pairing("T1", "U1")

    url = gmail_oauth.build_oauth_url("T1", "U1", token, code)
    query = parse_qs(urlparse(url).query)

    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "gmail.send" in url
    assert "openid+email" in url or "openid+email" in url.replace("%20", "+")
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    with pytest.raises(gmail_oauth.GmailOAuthError, match="pairing_code_mismatch"):
        gmail_oauth.build_oauth_url("T1", "U1", token, "BAD-CODE")


def test_confirmation_draft_encrypts_body() -> None:
    box = gmail_oauth.CryptoBox.from_env()
    ciphertext, nonce, _version = box.encrypt_json({"body": "sensitive email body"})

    assert b"sensitive email body" not in ciphertext
    assert box.decrypt_json(ciphertext, nonce)["body"] == "sensitive email body"


def test_button_value_binds_user() -> None:
    value = gmail_oauth.sign_button_value("00000000-0000-0000-0000-000000000001", "U1", "send")
    payload = gmail_oauth.verify_payload(value, expected_kind="gmail_confirm_button")

    assert payload["user"] == "U1"
    assert payload["action"] == "send"


@pytest.mark.asyncio
async def test_cross_user_button_click_rejected() -> None:
    pool = FakePool()
    value = gmail_oauth.sign_button_value("00000000-0000-0000-0000-000000000001", "U1", "send")

    with pytest.raises(gmail_oauth.GmailOAuthError, match="user_mismatch"):
        await gmail_oauth.handle_confirmation_action(
            pool,
            slack_team_id="T1",
            payload_user_id="U2",
            signed_value=value,
        )


@pytest.mark.asyncio
async def test_expired_button_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    box = gmail_oauth.CryptoBox.from_env()
    draft = {"to": ["a@example.com"], "cc": [], "bcc": [], "subject": "Hi", "body": "Body"}
    ciphertext, nonce, _version = box.encrypt_json(draft)
    confirmation_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    pool = FakePool(
        fetchrow_result={
            "id": confirmation_id,
            "status": "pending",
            "expires_at": datetime.now(UTC) - timedelta(seconds=1),
            "draft_ciphertext": ciphertext,
            "draft_nonce": nonce,
            "channel_id": "C1",
            "message_ts": "1.0",
        }
    )
    value = gmail_oauth.sign_button_value(str(confirmation_id), "U1", "send")

    with pytest.raises(gmail_oauth.GmailOAuthError, match="confirmation_expired"):
        await gmail_oauth.handle_confirmation_action(
            pool,
            slack_team_id="T1",
            payload_user_id="U1",
            signed_value=value,
        )

    assert any("status = 'expired'" in call[0] for call in pool.execute_calls)


@pytest.mark.asyncio
async def test_send_email_tool_resolves_exact_trigger_message_under_interleaved_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool(fetchrow_result={"user_id": "U1", "id": "msg:slack:T1:C1:1.0:slack:T1:C1:1.0"})
    monkeypatch.setattr(gmail_router.svc, "status", async_return({"state": "connected", "email": "u1@example.com"}))
    monkeypatch.setattr(gmail_router.svc, "create_confirmation", async_return({"confirmation_id": str(uuid.uuid4())}))
    monkeypatch.setattr(gmail_router.slackbot_client, "post", async_return({"ok": True}))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=pool)))
    body = gmail_router.SendEmailToolRequest(
        thread_key="slack:T1:C1:1.0",
        trigger_message_ts="1.0",
        to=["a@example.com"],
        subject="Subject",
        body="Body",
    )

    result = await gmail_router.send_email_tool(request, body)

    assert result["result"] == "confirmation_posted"
    assert pool.fetchrow_calls[0][1:] == ("slack:T1:C1:1.0", "msg:slack:T1:C1:1.0:slack:T1:C1:1.0")


@pytest.mark.asyncio
async def test_rate_limit_trip() -> None:
    pool = FakePool(fetchrow_result={"count": 11})

    with pytest.raises(gmail_oauth.GmailOAuthError, match="rate_limited"):
        await gmail_oauth.check_rate(pool, "pairing_user_hour", "T1", "U1", 10, 3600)


def test_oauth_state_signature_and_ttl_failures() -> None:
    expired = gmail_oauth.sign_payload({"kind": "gmail_oauth_state", "exp": int(time.time()) - 1})
    with pytest.raises(gmail_oauth.GmailOAuthError, match="expired_signed_payload"):
        gmail_oauth.verify_payload(expired, expected_kind="gmail_oauth_state")

    valid = gmail_oauth.sign_payload({"kind": "gmail_oauth_state", "exp": int(time.time()) + 60})
    with pytest.raises(gmail_oauth.GmailOAuthError, match="bad_signature"):
        gmail_oauth.verify_payload(f"{valid[:-1]}x", expected_kind="gmail_oauth_state")


@pytest.mark.asyncio
async def test_disconnect_calls_google_revoke_and_marks_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    box = gmail_oauth.CryptoBox.from_env()
    ciphertext, nonce, _version = box.encrypt(b"refresh-token")
    pool = FakePool(fetchrow_result={"refresh_token_ciphertext": ciphertext, "refresh_token_nonce": nonce})
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, data: dict[str, str]):
            calls.append((url, data))
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(gmail_oauth.httpx, "AsyncClient", FakeClient)

    await gmail_oauth.disconnect(pool, "T1", "U1")

    assert calls == [(gmail_oauth.GOOGLE_REVOKE_URL, {"token": "refresh-token"})]
    assert any("connection_status = 'revoked'" in call[0] for call in pool.execute_calls)


class FakePool:
    def __init__(self, fetchrow_result=None) -> None:
        self.fetchrow_result = fetchrow_result
        self.fetchrow_calls = []
        self.execute_calls = []

    async def fetchrow(self, sql: str, *args):
        self.fetchrow_calls.append((sql, *args))
        return self.fetchrow_result

    async def execute(self, sql: str, *args):
        self.execute_calls.append((sql, *args))
        return "OK"


def async_return(value):
    async def inner(*args, **kwargs):
        return value

    return inner
