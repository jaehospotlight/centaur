from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from api.deps import verify_api_key
from api.integrations import gmail_oauth as svc
from api import slackbot_client

router = APIRouter(prefix="/gmail-oauth", tags=["gmail-oauth"])
internal_router = APIRouter(
    prefix="/internal/gmail-oauth",
    tags=["gmail-oauth-internal"],
    dependencies=[Depends(verify_api_key)],
)


class Identity(BaseModel):
    slack_team_id: str
    slack_user_id: str


class BeginRequest(Identity):
    pairing_token: str
    pairing_code: str


class ConfirmationRequest(Identity):
    channel_id: str
    message_ts: str
    draft: dict[str, Any]


class ActionRequest(BaseModel):
    slack_team_id: str
    payload_user_id: str
    signed_value: str


class SendEmailToolRequest(BaseModel):
    thread_key: str
    trigger_message_ts: str
    to: list[str]
    cc: list[str] = []
    bcc: list[str] = []
    subject: str
    body: str
    attachments: list[dict[str, Any]] = []


@internal_router.post("/pairing")
async def pairing_with_request(request: Request, body: Identity) -> dict[str, str]:
    await svc.check_rate(
        request.app.state.db_pool,
        "pairing_user_hour",
        body.slack_team_id,
        body.slack_user_id,
        10,
        3600,
    )
    code, token = svc.build_pairing(body.slack_team_id, body.slack_user_id)
    return {"pairing_code": code, "pairing_token": token}


@internal_router.post("/begin")
async def begin(body: BeginRequest) -> dict[str, str]:
    return {
        "url": svc.build_oauth_url(
            body.slack_team_id,
            body.slack_user_id,
            body.pairing_token,
            body.pairing_code,
        )
    }


@internal_router.post("/status")
async def status(request: Request, body: Identity) -> dict[str, Any]:
    return await svc.status(request.app.state.db_pool, body.slack_team_id, body.slack_user_id)


@internal_router.post("/disconnect")
async def disconnect(request: Request, body: Identity) -> dict[str, bool]:
    await svc.disconnect(request.app.state.db_pool, body.slack_team_id, body.slack_user_id)
    return {"ok": True}


@internal_router.post("/confirmations")
async def create_confirmation(request: Request, body: ConfirmationRequest) -> dict[str, Any]:
    clean = {
        "to": [str(x) for x in body.draft.get("to", [])],
        "cc": [str(x) for x in body.draft.get("cc", [])],
        "bcc": [str(x) for x in body.draft.get("bcc", [])],
        "subject": str(body.draft.get("subject") or ""),
        "body": str(body.draft.get("body") or ""),
        "attachments": _clean_attachments(body.draft.get("attachments") or []),
    }
    result = await svc.create_confirmation(
        request.app.state.db_pool,
        body.slack_team_id,
        body.slack_user_id,
        body.channel_id,
        body.message_ts,
        clean,
    )
    result["send_value"] = svc.sign_button_value(result["confirmation_id"], body.slack_user_id, "send")
    result["cancel_value"] = svc.sign_button_value(result["confirmation_id"], body.slack_user_id, "cancel")
    return result


@internal_router.post("/actions")
async def action(request: Request, body: ActionRequest) -> dict[str, Any]:
    try:
        return await svc.handle_confirmation_action(
            request.app.state.db_pool,
            slack_team_id=body.slack_team_id,
            payload_user_id=body.payload_user_id,
            signed_value=body.signed_value,
        )
    except svc.GmailOAuthError as exc:
        if exc.code == "invalid_grant":
            return {"result": "connection_invalid"}
        raise HTTPException(status_code=400, detail=exc.code) from exc


@internal_router.post("/send-email-tool")
async def send_email_tool(request: Request, body: SendEmailToolRequest) -> dict[str, Any]:
    parts = body.thread_key.split(":")
    if len(parts) < 4 or parts[0] != "slack":
        raise HTTPException(status_code=400, detail="send_email_requires_slack_thread")
    slack_team_id, channel_id, thread_ts = parts[1], parts[2], parts[3]
    trigger_message_id = f"slack:{slack_team_id}:{channel_id}:{body.trigger_message_ts}"
    row = await request.app.state.db_pool.fetchrow(
        "SELECT user_id, id FROM chat_messages "
        "WHERE thread_key = $1 AND id = $2 AND role = 'user' AND user_id IS NOT NULL",
        body.thread_key,
        f"msg:{body.thread_key}:{trigger_message_id}",
    )
    if not row or not row["user_id"]:
        raise HTTPException(status_code=400, detail="verified_slack_user_not_found")
    slack_user_id = row["user_id"]
    st = await svc.status(request.app.state.db_pool, slack_team_id, slack_user_id)
    if st.get("state") != "connected":
        raise HTTPException(status_code=409, detail=st.get("state", "not_connected"))
    draft = {
        "to": body.to,
        "cc": body.cc,
        "bcc": body.bcc,
        "subject": body.subject,
        "body": body.body,
        "attachments": _clean_attachments(body.attachments),
    }
    confirmation = await svc.create_confirmation(
        request.app.state.db_pool,
        slack_team_id,
        slack_user_id,
        channel_id,
        thread_ts,
        draft,
    )
    send_value = svc.sign_button_value(confirmation["confirmation_id"], slack_user_id, "send")
    cancel_value = svc.sign_button_value(confirmation["confirmation_id"], slack_user_id, "cancel")
    await slackbot_client.post(
        "/api/slack/ephemeral",
        {
            "channel": channel_id,
            "user": slack_user_id,
            "thread_ts": thread_ts,
            "text": f"Confirm email to {', '.join(body.to)}: {body.subject}",
            "blocks": _confirmation_blocks(draft, send_value, cancel_value),
        },
    )
    return {"ok": True, "result": "confirmation_posted", "expires_in_seconds": svc.CONFIRMATION_TTL_S}


def _confirmation_blocks(draft: dict[str, Any], send_value: str, cancel_value: str) -> list[dict[str, Any]]:
    attachments = draft.get("attachments") or []
    attachment_names = [
        str(item.get("name") or item.get("attachment_id") or "attachment") for item in attachments
    ]
    preview = "\n".join(
        [
            f"*To:* {', '.join(draft['to'])}",
            f"*Cc:* {', '.join(draft['cc']) if draft['cc'] else '-'}",
            f"*Bcc:* {', '.join(draft['bcc']) if draft['bcc'] else '-'}",
            f"*Subject:* {draft['subject']}",
            f"*Attachments:* {', '.join(attachment_names) if attachment_names else '-'}",
            "",
            draft["body"],
        ]
    )
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": preview[:3000]}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Send"},
                    "action_id": "gmail_send_confirm",
                    "value": send_value,
                },
                {
                    "type": "button",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "action_id": "gmail_cancel_confirm",
                    "value": cancel_value,
                },
            ],
        },
    ]


def _clean_attachments(raw_attachments: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_attachments, list):
        raise HTTPException(status_code=400, detail="invalid_attachments")
    clean: list[dict[str, Any]] = []
    for raw in raw_attachments:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="invalid_attachments")
        attachment_id = raw.get("attachment_id") or raw.get("id")
        if attachment_id:
            clean.append(
                {
                    "attachment_id": str(attachment_id),
                    "name": str(raw.get("name") or attachment_id),
                    "mime_type": str(raw.get("mime_type") or "application/octet-stream"),
                }
            )
            continue
        data_base64 = raw.get("data_base64")
        if data_base64 is None:
            raise HTTPException(status_code=400, detail="invalid_attachments")
        clean.append(
            {
                "name": str(raw.get("name") or "attachment.bin"),
                "mime_type": str(raw.get("mime_type") or "application/octet-stream"),
                "data_base64": str(data_base64),
            }
        )
    return clean


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse("Gmail connection cancelled.")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing_code_or_state")
    payload = svc.verify_payload(state, expected_kind="gmail_oauth_state")
    verifier = svc.pkce_verifier(payload["team"], payload["user"], payload["nonce"], payload["pairing"])
    token_data = await svc.exchange_code_for_tokens(code, verifier)
    await svc.store_grant(request.app.state.db_pool, payload["team"], payload["user"], token_data)
    return HTMLResponse(
        "<h1>Gmail connected</h1>"
        f"<p>You connected Gmail for Slack user &lt;@{payload['user']}&gt;. "
        "Return to Slack to continue.</p>"
    )


@router.get("/begin")
async def public_begin():
    return RedirectResponse("/")
