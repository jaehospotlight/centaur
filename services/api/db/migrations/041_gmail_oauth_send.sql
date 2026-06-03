CREATE TABLE IF NOT EXISTS gmail_oauth_grants (
    slack_team_id TEXT NOT NULL,
    slack_user_id TEXT NOT NULL,
    google_subject TEXT,
    google_email TEXT,
    refresh_token_ciphertext BYTEA NOT NULL,
    refresh_token_nonce BYTEA NOT NULL,
    refresh_token_key_version TEXT NOT NULL,
    scope TEXT NOT NULL,
    connection_status TEXT NOT NULL DEFAULT 'connected'
        CHECK (connection_status IN ('connected', 'invalid', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    PRIMARY KEY (slack_team_id, slack_user_id)
);

CREATE TABLE IF NOT EXISTS gmail_send_confirmations (
    id UUID PRIMARY KEY,
    slack_team_id TEXT NOT NULL,
    slack_user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    draft_ciphertext BYTEA NOT NULL,
    draft_nonce BYTEA NOT NULL,
    draft_key_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'cancelled', 'expired', 'denied', 'invalidated')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS gmail_send_confirmations_lookup_idx
    ON gmail_send_confirmations (slack_team_id, slack_user_id, status, expires_at);

CREATE TABLE IF NOT EXISTS gmail_send_rate_limits (
    scope TEXT NOT NULL,
    slack_team_id TEXT NOT NULL,
    slack_user_id TEXT NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scope, slack_team_id, slack_user_id, bucket_start)
);
