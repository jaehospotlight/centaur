# Per-user Gmail OAuth send

Centaur can send Gmail messages only after the Slack user who asked for the send has connected Gmail and approved an ephemeral Send confirmation.

## User flow

1. Run `/ai-email-connect` in a public Slack channel.
2. Centaur replies ephemerally with the requested scope, a short pairing code, and a **Begin connection** button.
3. Enter the pairing code in Slack and click **Begin connection**. This prevents a leaked OAuth URL from binding an attacker-controlled Google account to the original Slack user.
4. Complete Google OAuth. The OAuth app requests `https://www.googleapis.com/auth/gmail.send` plus `openid email` so `/ai-email-status` can show the connected Google account.
5. Ask Centaur to send an email in a public channel. Centaur posts the full draft only as an ephemeral message to the verified Slack requester.
6. Click **Send** or **Cancel**. Buttons expire after 5 minutes.

`/ai-email-status` returns one of:

- `not_connected`
- `connected as <Google email>`
- `connection_invalid`

`/ai-email-disconnect` calls Google's token revocation endpoint, marks the local grant revoked, and invalidates pending confirmations.

## Security model

- Tokens are keyed only by `(slack_team_id, slack_user_id)` from Slack's verified payloads.
- The `send_email` tool accepts only `trigger_message_ts`, `to`, `cc`, `bcc`, `subject`, and `body`.
- The tool stages an ephemeral confirmation only. Email is not sent until the verified Slack requester clicks **Send**.
- Sender identity is derived server-side from the exact persisted Slack `trigger_message_ts` row and its verified `chat_messages.user_id`.
- OAuth state is HMAC-signed, TTL-bound, and tied to the initiating Slack user/team.
- OAuth authorization uses PKCE (`S256`), `access_type=offline`, `prompt=consent`, exact configured redirect URI, and no callback open redirect.
- Refresh tokens and pending draft confirmations are encrypted at rest with `GMAIL_OAUTH_TOKEN_ENCRYPTION_KEY`.
- Pending draft confirmation encryption covers body, recipients, subject, cc, and bcc.
- Access tokens are refreshed on demand and kept only in process memory.
- Reconnect invalidates all prior pending confirmations for that Slack user.
- `invalid_grant` marks the grant invalid; users are prompted to reconnect ephemerally.
- Google refresh-token rotation is persisted when Google returns a replacement refresh token.

## Existing infrastructure

- Token and confirmation storage: existing Centaur Postgres via `DATABASE_URL`.
- Encryption keys: existing secret injection / 1Password vault (`OP_VAULT`) with `GMAIL_OAUTH_TOKEN_ENCRYPTION_KEY`.
- Audit logging: existing structured logs / VictoriaLogs with event `gmail_oauth_send_audit`.
- Rate limiting: existing Postgres counter table, not a new cache/service.
- Slack interaction: existing Slackbot Hono service and Slack signature verification.
- OAuth callback: existing FastAPI API service.
- Ephemeral Slack posting can use a narrower `SLACKBOT_EPHEMERAL_API_KEY`; when configured, `/api/slack/ephemeral` rejects the broader Slackbot API key.

Google Workspace admin may need to approve the `gmail.send`, `openid`, and `email` scopes for the OAuth client before production use; this depends on the workspace's app access control policy.

## Rate limits

- Draft confirmation creation: 30/hour per Slack user.
- Sends: 20/hour and 100/day per Slack user.
- Pairing-token creation: 10/hour per Slack user.
- The DB counter design can also support a global circuit breaker by adding global scope rows without new infrastructure.
- Old rate-limit buckets are pruned from Postgres during rate-limit checks.

## Encryption key rotation

1. Add a new key to the existing secret store as `GMAIL_OAUTH_TOKEN_ENCRYPTION_KEY` and increment `GMAIL_OAUTH_TOKEN_KEY_VERSION`.
2. Deploy readers with access to both old and new keys if multi-key decrypt support is added; until then, perform rotation in a maintenance window.
3. Run a one-time re-encryption job that reads each grant/confirmation, decrypts with the old key, re-encrypts with the new key, and updates `*_key_version`.
4. Verify `/ai-email-status` and a test confirmation for a pilot user.
5. Remove the old key after all rows show the new key version and backups containing old ciphertext have aged out per retention policy.
