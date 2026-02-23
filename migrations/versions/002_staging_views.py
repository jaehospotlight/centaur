"""Staging views — dedup + JSON extraction per source.

Revision ID: 002
Revises: 001
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── stg_raw_latest: dedup to most recent per entity ────────────────
    op.execute("""
        CREATE VIEW stg_raw_latest AS
        SELECT DISTINCT ON (source, kind, external_id)
            source, kind, external_id, fetched_at, content_hash, data
        FROM raw_records
        ORDER BY source, kind, external_id, fetched_at DESC
    """)

    # ── Slack ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_slack_message AS
        SELECT
            external_id                          AS id,
            data->>'channel'                     AS channel_id,
            data->>'ts'                          AS slack_ts,
            (data->>'ts')::timestamptz           AS occurred_at,
            data->>'user'                        AS user_id,
            data->>'text'                        AS text,
            data->>'thread_ts'                   AS thread_ts,
            (data->>'reply_count')::int          AS reply_count,
            data->>'subtype'                     AS subtype,
            'https://tempoxyz.slack.com/archives/' || (data->>'channel')
                || '/p' || REPLACE(data->>'ts', '.', '') AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'slack' AND kind = 'message'
    """)

    op.execute("""
        CREATE VIEW stg_slack_channel AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            (data->>'is_shared')::boolean        AS is_shared,
            data->>'topic'                       AS topic,
            data->>'purpose'                     AS purpose,
            (data->>'num_members')::int          AS member_count,
            'https://tempoxyz.slack.com/archives/' || external_id AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'slack' AND kind = 'channel'
    """)

    op.execute("""
        CREATE VIEW stg_slack_user AS
        SELECT
            external_id                                           AS id,
            COALESCE(data->'profile'->>'real_name', data->>'name') AS real_name,
            data->'profile'->>'display_name'                      AS display_name,
            data->'profile'->>'email'                             AS email,
            (data->>'is_bot')::boolean                            AS is_bot,
            NULL                                                  AS url,
            data                                                  AS raw_json
        FROM stg_raw_latest
        WHERE source = 'slack' AND kind = 'user'
    """)

    # ── GitHub ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_github_pr AS
        SELECT
            external_id                          AS id,
            data->'base'->'repo'->>'full_name'   AS repo,
            (data->>'number')::int               AS number,
            data->>'title'                       AS title,
            data->>'body'                        AS body,
            data->>'state'                       AS pr_state,
            data->>'html_url'                    AS url,
            data->'user'->>'login'               AS author_login,
            (data->>'created_at')::timestamptz   AS created_at,
            (data->>'updated_at')::timestamptz   AS updated_at,
            (data->>'merged_at')::timestamptz    AS merged_at,
            (data->>'closed_at')::timestamptz    AS closed_at,
            data->>'requested_reviewers'         AS reviewers_json,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'github' AND kind = 'pull_request'
    """)

    op.execute("""
        CREATE VIEW stg_github_repo AS
        SELECT
            external_id                          AS id,
            data->>'full_name'                   AS full_name,
            data->>'name'                        AS name,
            data->>'html_url'                    AS url,
            data->>'language'                    AS language,
            (data->>'stargazers_count')::int     AS stars,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'github' AND kind = 'repo'
    """)

    op.execute("""
        CREATE VIEW stg_github_member AS
        SELECT
            external_id                          AS id,
            data->>'login'                       AS login,
            data->>'html_url'                    AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'github' AND kind = 'member'
    """)

    op.execute("""
        CREATE VIEW stg_github_user AS
        SELECT
            external_id                          AS id,
            data->>'login'                       AS login,
            data->>'name'                        AS name,
            data->>'email'                       AS email,
            data->>'html_url'                    AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'github' AND kind = 'user'
    """)

    # ── Linear ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_linear_issue AS
        SELECT
            external_id                          AS id,
            data->>'identifier'                  AS identifier,
            data->>'title'                       AS title,
            data->>'description'                 AS description,
            data->>'priorityLabel'               AS priority_label,
            data->'state'->>'id'                 AS state_id,
            data->'assignee'->>'id'              AS assignee_id,
            data->'project'->>'id'               AS project_id,
            (data->>'createdAt')::timestamptz    AS created_at,
            (data->>'updatedAt')::timestamptz    AS updated_at,
            (data->>'completedAt')::timestamptz  AS completed_at,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'linear' AND kind = 'issue'
    """)

    op.execute("""
        CREATE VIEW stg_linear_project AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'description'                 AS description,
            data->>'state'                       AS state,
            data->>'url'                         AS url,
            (data->>'progress')::float           AS progress,
            data->'lead'->>'id'                  AS lead_id,
            (data->>'startDate')::date           AS start_date,
            (data->>'targetDate')::date          AS target_date,
            (data->>'createdAt')::timestamptz    AS created_at,
            (data->>'updatedAt')::timestamptz    AS updated_at,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'linear' AND kind = 'project'
    """)

    op.execute("""
        CREATE VIEW stg_linear_comment AS
        SELECT
            external_id                          AS id,
            data->>'body'                        AS body,
            data->'issue'->>'id'                 AS issue_id,
            data->'user'->>'id'                  AS user_id,
            (data->>'createdAt')::timestamptz    AS created_at,
            (data->>'updatedAt')::timestamptz    AS updated_at,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'linear' AND kind = 'comment'
    """)

    op.execute("""
        CREATE VIEW stg_linear_workflow_state AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'type'                        AS type,
            data->>'color'                       AS color,
            data->'team'->>'id'                  AS team_id,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'linear' AND kind = 'workflow_state'
    """)

    op.execute("""
        CREATE VIEW stg_linear_user AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'displayName'                 AS display_name,
            data->>'email'                       AS email,
            (data->>'active')::boolean           AS is_active,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'linear' AND kind = 'user'
    """)

    # ── GCal ───────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_gcal_event AS
        SELECT
            external_id                          AS id,
            data->>'summary'                     AS title,
            data->>'description'                 AS description,
            COALESCE(
                (data->'start'->>'dateTime')::timestamptz,
                (data->'start'->>'date')::timestamptz
            )                                    AS start_at,
            COALESCE(
                (data->'end'->>'dateTime')::timestamptz,
                (data->'end'->>'date')::timestamptz
            )                                    AS end_at,
            data->>'status'                      AS status,
            data->'organizer'->>'email'          AS organizer_email,
            data->>'htmlLink'                    AS url,
            data->>'calendarId'                  AS calendar_id,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'gcal' AND kind = 'event'
    """)

    op.execute("""
        CREATE VIEW stg_gcal_attendee AS
        SELECT
            external_id                          AS id,
            data->>'event_id'                    AS event_id,
            data->>'email'                       AS email,
            data->>'displayName'                 AS display_name,
            data->>'responseStatus'              AS response_status,
            (data->>'organizer')::boolean        AS is_organizer,
            NULL                                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'gcal' AND kind = 'attendee'
    """)

    # ── GDrive ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_gdrive_doc AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'mimeType'                    AS mime_type,
            (data->>'modifiedTime')::timestamptz AS modified_at,
            data->>'webViewLink'                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'gdrive' AND kind = 'doc'
    """)

    op.execute("""
        CREATE VIEW stg_gdrive_file AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'mimeType'                    AS mime_type,
            (data->>'modifiedTime')::timestamptz AS modified_at,
            data->'lastModifyingUser'->>'emailAddress' AS last_modifier_email,
            data->>'webViewLink'                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'gdrive' AND kind = 'file'
    """)

    # ── Gmail ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_gmail_message AS
        SELECT
            external_id                          AS id,
            data->>'threadId'                    AS thread_id,
            data->>'subject'                     AS subject,
            data->>'from'                        AS from_header,
            data->>'snippet'                     AS snippet,
            (data->>'internalDate')::timestamptz AS occurred_at,
            NULL                                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'gmail' AND kind = 'message'
    """)

    op.execute("""
        CREATE VIEW stg_gmail_thread AS
        SELECT
            external_id                          AS id,
            data->>'snippet'                     AS snippet,
            (data->>'historyId')::bigint         AS history_id,
            NULL                                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'gmail' AND kind = 'thread'
    """)

    # ── Granola ────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_granola_meeting AS
        SELECT
            external_id                          AS id,
            data->>'title'                       AS title,
            (data->>'created_at')::timestamptz   AS created_at,
            (data->>'gcal_start_at')::timestamptz AS gcal_start_at,
            data->>'notes_plain'                 AS notes_plain,
            data->>'notes_markdown'              AS notes_markdown,
            CASE WHEN LENGTH(COALESCE(data->>'notes_plain', '')) > 20
                 THEN TRUE ELSE FALSE END        AS is_valid,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'granola' AND kind = 'meeting'
    """)

    op.execute("""
        CREATE VIEW stg_granola_transcript AS
        SELECT
            external_id                          AS id,
            data->>'meeting_id'                  AS meeting_id,
            data->>'text'                        AS text,
            data->>'speaker'                     AS speaker,
            (data->>'start_time')::float         AS start_time,
            NULL                                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'granola' AND kind = 'transcript'
    """)

    # ── Attio ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_attio_company AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'description'                 AS description,
            data->>'domain'                      AS domain,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'attio' AND kind = 'company'
    """)

    op.execute("""
        CREATE VIEW stg_attio_person AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'email'                       AS email,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'attio' AND kind = 'person'
    """)

    op.execute("""
        CREATE VIEW stg_attio_deal AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'stage'                       AS stage,
            (data->>'value')::float              AS value,
            data->>'currency'                    AS currency,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'attio' AND kind = 'deal'
    """)

    # ── Pylon ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_pylon_issue AS
        SELECT
            external_id                          AS id,
            data->>'title'                       AS title,
            data->>'state'                       AS state,
            data->>'priority'                    AS priority,
            data->'account'->>'name'             AS account_name,
            (data->>'created_at')::timestamptz   AS created_at,
            (data->>'updated_at')::timestamptz   AS updated_at,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'pylon' AND kind = 'issue'
    """)

    op.execute("""
        CREATE VIEW stg_pylon_message AS
        SELECT
            external_id                          AS id,
            data->>'issue_id'                    AS issue_id,
            data->>'body'                        AS body,
            data->>'author_name'                 AS author_name,
            (data->>'created_at')::timestamptz   AS created_at,
            NULL                                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'pylon' AND kind = 'message'
    """)

    op.execute("""
        CREATE VIEW stg_pylon_account AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'domain'                      AS domain,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'pylon' AND kind = 'account'
    """)

    # ── BetterStack ────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW stg_betterstack_incident AS
        SELECT
            external_id                          AS id,
            data->>'name'                        AS name,
            data->>'cause'                       AS cause,
            (data->>'started_at')::timestamptz   AS started_at,
            (data->>'resolved_at')::timestamptz  AS resolved_at,
            data->>'url'                         AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'betterstack' AND kind = 'incident'
    """)

    op.execute("""
        CREATE VIEW stg_betterstack_monitor AS
        SELECT
            external_id                          AS id,
            data->>'url'                         AS monitor_url,
            data->>'pronounceable_name'          AS name,
            data->>'status'                      AS status,
            (data->>'last_checked_at')::timestamptz AS last_checked_at,
            NULL                                 AS url,
            data                                 AS raw_json
        FROM stg_raw_latest
        WHERE source = 'betterstack' AND kind = 'monitor'
    """)


def downgrade() -> None:
    views = [
        "stg_betterstack_monitor", "stg_betterstack_incident",
        "stg_pylon_account", "stg_pylon_message", "stg_pylon_issue",
        "stg_attio_deal", "stg_attio_person", "stg_attio_company",
        "stg_granola_transcript", "stg_granola_meeting",
        "stg_gmail_thread", "stg_gmail_message",
        "stg_gdrive_file", "stg_gdrive_doc",
        "stg_gcal_attendee", "stg_gcal_event",
        "stg_linear_user", "stg_linear_workflow_state",
        "stg_linear_comment", "stg_linear_project", "stg_linear_issue",
        "stg_github_user", "stg_github_member", "stg_github_repo", "stg_github_pr",
        "stg_slack_user", "stg_slack_channel", "stg_slack_message",
        "stg_raw_latest",
    ]
    for v in views:
        op.execute(f"DROP VIEW IF EXISTS {v} CASCADE")
