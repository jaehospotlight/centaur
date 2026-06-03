from __future__ import annotations

import asyncio
import json

import typer

from client import SendEmailClient

app = typer.Typer()


@app.command("send_email")
def send_email(
    trigger_message_ts: str = typer.Option(..., help="Exact Slack timestamp of the triggering message."),
    to: list[str] = typer.Option(..., help="Recipient email address. Repeat for multiple recipients."),
    subject: str = typer.Option(...),
    body: str = typer.Option(...),
    cc: list[str] = typer.Option([], help="CC recipient. Repeat for multiple recipients."),
    bcc: list[str] = typer.Option([], help="BCC recipient. Repeat for multiple recipients."),
) -> None:
    result = asyncio.run(
        SendEmailClient().send_email(
            trigger_message_ts=trigger_message_ts,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
        )
    )
    print(json.dumps(result))


if __name__ == "__main__":
    app()
