from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_EMAIL_SCOPES = "openid email"
GOOGLE_OAUTH_SCOPES = f"{GMAIL_SEND_SCOPE} {GOOGLE_EMAIL_SCOPES}"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

STATE_TTL_S = 10 * 60
CONNECT_PAIRING_TTL_S = 10 * 60
CONFIRMATION_TTL_S = 5 * 60

log = structlog.get_logger().bind(component="gmail_oauth")


class GmailOAuthError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class CryptoBox:
    key: bytes
    key_version: str

    @classmethod
    def from_env(cls) -> "CryptoBox":
        raw = os.environ.get("GMAIL_OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
        version = os.environ.get("GMAIL_OAUTH_TOKEN_KEY_VERSION", "v1").strip() or "v1"
        if not raw:
            raise GmailOAuthError("encryption_key_missing")
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except Exception:
            key = b""
        if len(key) not in (16, 24, 32):
            digest = hashlib.sha256(raw.encode()).digest()
            key = digest
        return cls(key=key, key_version=version)

    def encrypt_json(self, value: dict[str, Any]) -> tuple[bytes, bytes, str]:
        return self.encrypt(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())

    def decrypt_json(self, ciphertext: bytes, nonce: bytes) -> dict[str, Any]:
        return json.loads(self.decrypt(ciphertext, nonce).decode())

    def encrypt(self, plaintext: bytes) -> tuple[bytes, bytes, str]:
        nonce = os.urandom(12)
        return AESGCM(self.key).encrypt(nonce, plaintext, None), nonce, self.key_version

    def decrypt(self, ciphertext: bytes, nonce: bytes) -> bytes:
        return AESGCM(self.key).decrypt(nonce, ciphertext, None)


def _signing_key() -> bytes:
    key = (
        os.environ.get("GMAIL_OAUTH_STATE_SIGNING_KEY")
        or os.environ.get("API_SECRET_KEY")
        or os.environ.get("SANDBOX_SIGNING_KEY")
        or ""
    ).strip()
    if not key:
        raise GmailOAuthError("state_signing_key_missing")
    return key.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_payload(payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def verify_payload(token: str, *, expected_kind: str | None = None) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            raise GmailOAuthError("bad_signature")
        payload = json.loads(_unb64(body))
    except GmailOAuthError:
        raise
    except Exception as exc:
        raise GmailOAuthError("invalid_signed_payload") from exc
    if expected_kind and payload.get("kind") != expected_kind:
        raise GmailOAuthError("wrong_payload_kind")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise GmailOAuthError("expired_signed_payload")
    return payload


def build_pairing(slack_team_id: str, slack_user_id: str) -> tuple[str, str]:
    code = f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:3]}".upper()
    payload = {
        "kind": "gmail_pairing",
        "team": slack_team_id,
        "user": slack_user_id,
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        "iat": int(time.time()),
        "exp": int(time.time()) + CONNECT_PAIRING_TTL_S,
        "nonce": uuid.uuid4().hex,
    }
    return code, sign_payload(payload)


def build_oauth_url(slack_team_id: str, slack_user_id: str, pairing_token: str, code: str) -> str:
    pairing = verify_payload(pairing_token, expected_kind="gmail_pairing")
    if pairing["team"] != slack_team_id or pairing["user"] != slack_user_id:
        raise GmailOAuthError("pairing_identity_mismatch")
    if pairing["code_hash"] != hashlib.sha256(code.strip().upper().encode()).hexdigest():
        raise GmailOAuthError("pairing_code_mismatch")
    nonce = uuid.uuid4().hex
    pairing_hash = hashlib.sha256(pairing_token.encode()).hexdigest()
    verifier = pkce_verifier(slack_team_id, slack_user_id, nonce, pairing_hash)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    state = sign_payload(
        {
            "kind": "gmail_oauth_state",
            "team": slack_team_id,
            "user": slack_user_id,
            "pairing": pairing_hash,
            "iat": int(time.time()),
            "exp": int(time.time()) + STATE_TTL_S,
            "nonce": nonce,
        }
    )
    redirect_uri = os.environ.get("GMAIL_OAUTH_REDIRECT_URI", "").strip()
    client_id = os.environ.get("GMAIL_OAUTH_CLIENT_ID", "").strip()
    if not redirect_uri or not client_id:
        raise GmailOAuthError("oauth_client_not_configured")
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': GOOGLE_OAUTH_SCOPES,
        'state': state,
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'false',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def pkce_verifier(slack_team_id: str, slack_user_id: str, nonce: str, pairing_hash: str) -> str:
    material = f"gmail-pkce:{slack_team_id}:{slack_user_id}:{nonce}:{pairing_hash}"
    digest = hmac.new(_signing_key(), material.encode(), hashlib.sha256).digest()
    return _b64(digest)


async def exchange_code_for_tokens(code: str, code_verifier: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": os.environ.get("GMAIL_OAUTH_CLIENT_ID", ""),
                "client_secret": os.environ.get("GMAIL_OAUTH_CLIENT_SECRET", ""),
                "redirect_uri": os.environ.get("GMAIL_OAUTH_REDIRECT_URI", ""),
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
    data = response.json()
    if response.status_code >= 400:
        raise GmailOAuthError(str(data.get("error") or "token_exchange_failed"))
    if data.get("access_token"):
        data["email"] = await fetch_token_email(str(data["access_token"]))
    return data


async def fetch_token_email(access_token: str) -> str | None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(GOOGLE_TOKENINFO_URL, params={"access_token": access_token})
    if response.status_code >= 400:
        return None
    data = response.json()
    email = data.get("email")
    return str(email) if email else None


async def refresh_access_token(pool: Any, slack_team_id: str, slack_user_id: str) -> str:
    row = await pool.fetchrow(
        "SELECT refresh_token_ciphertext, refresh_token_nonce FROM gmail_oauth_grants "
        "WHERE slack_team_id = $1 AND slack_user_id = $2 AND revoked_at IS NULL",
        slack_team_id,
        slack_user_id,
    )
    if not row:
        raise GmailOAuthError("not_connected")
    refresh_token = CryptoBox.from_env().decrypt(
        bytes(row["refresh_token_ciphertext"]), bytes(row["refresh_token_nonce"])
    ).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": os.environ.get("GMAIL_OAUTH_CLIENT_ID", ""),
                "client_secret": os.environ.get("GMAIL_OAUTH_CLIENT_SECRET", ""),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    data = response.json()
    if response.status_code >= 400:
        if data.get("error") == "invalid_grant":
            await mark_invalid(pool, slack_team_id, slack_user_id)
            raise GmailOAuthError("invalid_grant")
        raise GmailOAuthError(str(data.get("error") or "refresh_failed"))
    if data.get("refresh_token"):
        await store_grant(pool, slack_team_id, slack_user_id, data, invalidate_pending=False)
    return str(data["access_token"])


async def store_grant(
    pool: Any,
    slack_team_id: str,
    slack_user_id: str,
    token_data: dict[str, Any],
    *,
    invalidate_pending: bool = True,
) -> None:
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise GmailOAuthError("missing_refresh_token")
    box = CryptoBox.from_env()
    ciphertext, nonce, key_version = box.encrypt(str(refresh_token).encode())
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO gmail_oauth_grants (
                    slack_team_id, slack_user_id, google_subject, google_email,
                    refresh_token_ciphertext, refresh_token_nonce, refresh_token_key_version,
                    scope, connection_status, revoked_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'connected', NULL, NOW())
                ON CONFLICT (slack_team_id, slack_user_id) DO UPDATE SET
                    google_subject = EXCLUDED.google_subject,
                    google_email = EXCLUDED.google_email,
                    refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                    refresh_token_nonce = EXCLUDED.refresh_token_nonce,
                    refresh_token_key_version = EXCLUDED.refresh_token_key_version,
                    scope = EXCLUDED.scope,
                    connection_status = 'connected',
                    revoked_at = NULL,
                    updated_at = NOW()
                """,
                slack_team_id,
                slack_user_id,
                token_data.get("id_token_sub"),
                token_data.get("email"),
                ciphertext,
                nonce,
                key_version,
                str(token_data.get("scope") or GOOGLE_OAUTH_SCOPES),
            )
            if invalidate_pending:
                await conn.execute(
                    "UPDATE gmail_send_confirmations SET status = 'invalidated', updated_at = NOW() "
                    "WHERE slack_team_id = $1 AND slack_user_id = $2 AND status = 'pending'",
                    slack_team_id,
                    slack_user_id,
                )


async def status(pool: Any, slack_team_id: str, slack_user_id: str) -> dict[str, Any]:
    row = await pool.fetchrow(
        "SELECT google_email, connection_status, revoked_at FROM gmail_oauth_grants "
        "WHERE slack_team_id = $1 AND slack_user_id = $2",
        slack_team_id,
        slack_user_id,
    )
    if not row or row["revoked_at"] is not None:
        return {"state": "not_connected"}
    if row["connection_status"] == "invalid":
        return {"state": "connection_invalid", "email": row["google_email"]}
    return {"state": "connected", "email": row["google_email"]}


async def mark_invalid(pool: Any, slack_team_id: str, slack_user_id: str) -> None:
    await pool.execute(
        "UPDATE gmail_oauth_grants SET connection_status = 'invalid', updated_at = NOW() "
        "WHERE slack_team_id = $1 AND slack_user_id = $2",
        slack_team_id,
        slack_user_id,
    )


async def disconnect(pool: Any, slack_team_id: str, slack_user_id: str) -> None:
    row = await pool.fetchrow(
        "SELECT refresh_token_ciphertext, refresh_token_nonce FROM gmail_oauth_grants "
        "WHERE slack_team_id = $1 AND slack_user_id = $2 AND revoked_at IS NULL",
        slack_team_id,
        slack_user_id,
    )
    if row:
        try:
            token = CryptoBox.from_env().decrypt(
                bytes(row["refresh_token_ciphertext"]), bytes(row["refresh_token_nonce"])
            ).decode()
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(GOOGLE_REVOKE_URL, data={"token": token})
        except Exception as exc:
            log.warning("gmail_revoke_failed_local_disconnect_continues", error=str(exc))
    await pool.execute(
        "UPDATE gmail_oauth_grants SET connection_status = 'revoked', revoked_at = NOW(), updated_at = NOW() "
        "WHERE slack_team_id = $1 AND slack_user_id = $2",
        slack_team_id,
        slack_user_id,
    )
    await pool.execute(
        "UPDATE gmail_send_confirmations SET status = 'invalidated', updated_at = NOW() "
        "WHERE slack_team_id = $1 AND slack_user_id = $2 AND status = 'pending'",
        slack_team_id,
        slack_user_id,
    )


async def check_rate(pool: Any, scope: str, slack_team_id: str, slack_user_id: str, limit: int, window_s: int) -> None:
    bucket = int(time.time() // window_s * window_s)
    await pool.execute(
        "DELETE FROM gmail_send_rate_limits WHERE updated_at < NOW() - INTERVAL '14 days'"
    )
    row = await pool.fetchrow(
        """
        INSERT INTO gmail_send_rate_limits (scope, slack_team_id, slack_user_id, bucket_start, count, updated_at)
        VALUES ($1, $2, $3, to_timestamp($4), 1, NOW())
        ON CONFLICT (scope, slack_team_id, slack_user_id, bucket_start)
        DO UPDATE SET count = gmail_send_rate_limits.count + 1, updated_at = NOW()
        RETURNING count
        """,
        scope,
        slack_team_id,
        slack_user_id,
        bucket,
    )
    if int(row["count"]) > limit:
        raise GmailOAuthError("rate_limited")


async def create_confirmation(
    pool: Any,
    slack_team_id: str,
    slack_user_id: str,
    channel_id: str,
    message_ts: str,
    draft: dict[str, Any],
) -> dict[str, Any]:
    await check_rate(pool, "draft_user_hour", slack_team_id, slack_user_id, 30, 3600)
    box = CryptoBox.from_env()
    ciphertext, nonce, key_version = box.encrypt_json(draft)
    cid = str(uuid.uuid4())
    await pool.execute(
        """
        INSERT INTO gmail_send_confirmations (
            id, slack_team_id, slack_user_id, channel_id, message_ts,
            draft_ciphertext, draft_nonce, draft_key_version, expires_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW() + ($9 || ' seconds')::interval)
        """,
        uuid.UUID(cid),
        slack_team_id,
        slack_user_id,
        channel_id,
        message_ts,
        ciphertext,
        nonce,
        key_version,
        CONFIRMATION_TTL_S,
    )
    return {"confirmation_id": cid, "expires_at_s": CONFIRMATION_TTL_S}


def sign_button_value(confirmation_id: str, slack_user_id: str, action: str) -> str:
    return sign_payload(
        {
            "kind": "gmail_confirm_button",
            "confirmation_id": confirmation_id,
            "user": slack_user_id,
            "action": action,
            "exp": int(time.time()) + CONFIRMATION_TTL_S,
        }
    )


async def handle_confirmation_action(
    pool: Any,
    *,
    slack_team_id: str,
    payload_user_id: str,
    signed_value: str,
) -> dict[str, Any]:
    value = verify_payload(signed_value, expected_kind="gmail_confirm_button")
    if value["user"] != payload_user_id:
        await audit(pool, slack_team_id, payload_user_id, "", "", [], "", "denied-due-to-mismatch")
        raise GmailOAuthError("user_mismatch")
    if value["action"] == "cancel":
        await pool.execute(
            "UPDATE gmail_send_confirmations SET status = 'cancelled', updated_at = NOW() "
            "WHERE id = $1 AND slack_team_id = $2 AND slack_user_id = $3 AND status = 'pending'",
            uuid.UUID(value["confirmation_id"]),
            slack_team_id,
            payload_user_id,
        )
        return {"result": "cancelled"}
    row = await pool.fetchrow(
        "SELECT * FROM gmail_send_confirmations WHERE id = $1 AND slack_team_id = $2 AND slack_user_id = $3",
        uuid.UUID(value["confirmation_id"]),
        slack_team_id,
        payload_user_id,
    )
    if not row or row["status"] != "pending":
        raise GmailOAuthError("confirmation_not_pending")
    if row["expires_at"].timestamp() < time.time():
        await pool.execute("UPDATE gmail_send_confirmations SET status = 'expired', updated_at = NOW() WHERE id = $1", row["id"])
        draft = CryptoBox.from_env().decrypt_json(bytes(row["draft_ciphertext"]), bytes(row["draft_nonce"]))
        await audit(pool, slack_team_id, payload_user_id, row["channel_id"], row["message_ts"], _draft_recipients(draft), str(draft.get("subject") or ""), "expired-button")
        raise GmailOAuthError("confirmation_expired")
    await check_rate(pool, "send_user_hour", slack_team_id, payload_user_id, 20, 3600)
    await check_rate(pool, "send_user_day", slack_team_id, payload_user_id, 100, 86400)
    await check_rate(pool, "send_global_hour", slack_team_id, "*", int(os.environ.get("GMAIL_SEND_GLOBAL_HOURLY_LIMIT", "500")), 3600)
    draft = CryptoBox.from_env().decrypt_json(bytes(row["draft_ciphertext"]), bytes(row["draft_nonce"]))
    access_token = await refresh_access_token(pool, slack_team_id, payload_user_id)
    await send_gmail(access_token, draft)
    await pool.execute("UPDATE gmail_send_confirmations SET status = 'sent', updated_at = NOW() WHERE id = $1", row["id"])
    await audit(pool, slack_team_id, payload_user_id, row["channel_id"], row["message_ts"], _draft_recipients(draft), str(draft.get("subject") or ""), "success")
    return {"result": "sent"}


def _draft_recipients(draft: dict[str, Any]) -> list[str]:
    return [str(x) for key in ("to", "cc", "bcc") for x in draft.get(key, [])]


async def audit(
    pool: Any,
    slack_team_id: str,
    slack_user_id: str,
    channel_id: str,
    message_ts: str,
    recipients: list[str],
    subject: str,
    result: str,
) -> None:
    log.info(
        "gmail_oauth_send_audit",
        slack_team_id=slack_team_id,
        slack_user_id=slack_user_id,
        channel_id=channel_id,
        message_ts=message_ts,
        recipients=recipients,
        subject=subject,
        result=result,
    )


async def send_gmail(access_token: str, draft: dict[str, Any]) -> None:
    msg = EmailMessage()
    msg["To"] = ", ".join(draft.get("to") or [])
    if draft.get("cc"):
        msg["Cc"] = ", ".join(draft["cc"])
    if draft.get("bcc"):
        msg["Bcc"] = ", ".join(draft["bcc"])
    msg["Subject"] = str(draft.get("subject") or "")
    msg.set_content(str(draft.get("body") or ""))
    raw = _b64(msg.as_bytes())
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
        )
    if response.status_code >= 400:
        raise GmailOAuthError("gmail_send_failed")
