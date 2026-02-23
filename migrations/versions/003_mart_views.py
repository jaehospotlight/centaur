"""Mart materialized views — cross-source joins and aggregations.

Revision ID: 003
Revises: 002
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Entity map (bridge: entity_mappings as a view) ─────────────────
    op.execute("""
        CREATE VIEW mart_entity_map AS
        SELECT source, external_id, person_slug
        FROM entity_mappings
    """)

    # ── Slack message (pre-joined) ─────────────────────────────────────
    op.execute("""
        CREATE VIEW mart_slack_message AS
        SELECT
            m.id,
            m.channel_id,
            c.name                  AS channel_name,
            m.slack_ts,
            m.occurred_at,
            m.user_id,
            u.real_name,
            m.text,
            m.thread_ts,
            m.reply_count,
            m.subtype,
            m.url
        FROM stg_slack_message m
        LEFT JOIN stg_slack_channel c ON c.id = m.channel_id
        LEFT JOIN stg_slack_user u ON u.id = m.user_id
    """)

    # ── Slack thread aggregation ───────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_slack_thread AS
        WITH thread_agg AS (
            SELECT
                m.channel_id,
                m.thread_ts,
                MIN(m.occurred_at)                             AS started_at,
                MAX(m.occurred_at)                             AS last_reply_at,
                COUNT(*) - 1                                   AS reply_count,
                COUNT(DISTINCT m.user_id)                      AS participant_count,
                string_agg(DISTINCT u.real_name, ', ')         AS participant_names,
                string_agg(DISTINCT em.person_slug, ', ')      AS participant_slugs,
                string_agg(m.text, E'\n' ORDER BY m.occurred_at) AS all_text,
                SUM(CASE WHEN u.is_bot THEN 1 ELSE 0 END)     AS bot_message_count,
                COUNT(DISTINCT CASE WHEN NOT COALESCE(u.is_bot, FALSE) THEN m.user_id END)
                                                               AS human_participant_count
            FROM stg_slack_message m
            LEFT JOIN stg_slack_user u ON u.id = m.user_id
            LEFT JOIN mart_entity_map em ON em.source = 'slack' AND em.external_id = m.user_id
            WHERE m.thread_ts IS NOT NULL AND m.thread_ts != ''
            GROUP BY m.channel_id, m.thread_ts
        ),
        parent AS (
            SELECT DISTINCT ON (m.channel_id, m.thread_ts)
                m.channel_id,
                m.thread_ts,
                m.user_id      AS starter_user_id,
                m.text         AS parent_text,
                u.real_name    AS starter_name,
                em.person_slug AS starter_slug
            FROM stg_slack_message m
            LEFT JOIN stg_slack_user u ON u.id = m.user_id
            LEFT JOIN mart_entity_map em ON em.source = 'slack' AND em.external_id = m.user_id
            WHERE m.thread_ts IS NOT NULL AND m.thread_ts != ''
              AND m.slack_ts = m.thread_ts
            ORDER BY m.channel_id, m.thread_ts
        )
        SELECT
            t.channel_id,
            c.name                                             AS channel_name,
            t.thread_ts,
            t.started_at,
            t.last_reply_at,
            t.reply_count,
            t.participant_count,
            t.participant_names,
            t.participant_slugs,
            p.starter_user_id,
            p.starter_name,
            p.starter_slug,
            p.parent_text,
            t.all_text,
            t.bot_message_count,
            t.human_participant_count,
            t.bot_message_count::float / GREATEST(t.reply_count + 1, 1)
                                                               AS bot_ratio,
            CASE WHEN t.bot_message_count > t.reply_count + 1 - t.bot_message_count
                 THEN TRUE ELSE FALSE END                      AS is_noisy,
            CASE WHEN t.all_text ~* '(we decided|decision:|resolved:|we will|going with|final answer|ship it|confirmed:)'
                 THEN TRUE ELSE FALSE END                      AS has_decision_keywords,
            CASE WHEN t.all_text ~* '(spec|proposal|RFC|design doc|ADR|TIP-)'
                 THEN TRUE ELSE FALSE END                      AS has_spec_keywords,
            (LENGTH(t.all_text) - LENGTH(REPLACE(t.all_text, 'http', ''))) / 4
                                                               AS link_count,
            'https://tempoxyz.slack.com/archives/' || t.channel_id
                || '/p' || REPLACE(t.thread_ts, '.', '')       AS url
        FROM thread_agg t
        LEFT JOIN stg_slack_channel c ON c.id = t.channel_id
        LEFT JOIN parent p ON p.channel_id = t.channel_id AND p.thread_ts = t.thread_ts
    """)
    op.execute(
        "CREATE UNIQUE INDEX idx_mart_thread_pk ON mart_slack_thread (channel_id, thread_ts)"
    )
    op.execute("CREATE INDEX idx_mart_thread_started ON mart_slack_thread (started_at)")
    op.execute("CREATE INDEX idx_mart_thread_last ON mart_slack_thread (last_reply_at)")

    # ── Activity timeline (unified) ────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_activity_timeline AS
        -- GitHub PRs
        SELECT 'github' AS source, 'pr' AS kind, pr.id AS source_id,
               COALESCE(pr.merged_at, pr.updated_at, pr.created_at) AS occurred_at,
               pr.title, pr.body, pr.url,
               pr.author_login AS actor_external_id, 'github' AS actor_source,
               em.person_slug AS actor_slug
        FROM stg_github_pr pr
        LEFT JOIN mart_entity_map em ON em.source = 'github' AND em.external_id = pr.author_login
        UNION ALL
        -- GCal events
        SELECT 'gcal', 'event', ev.id, ev.start_at, ev.title, ev.description, ev.url,
               ev.organizer_email, 'email', em.person_slug
        FROM stg_gcal_event ev
        LEFT JOIN mart_entity_map em ON em.source = 'email' AND em.external_id = ev.organizer_email
        UNION ALL
        -- Linear issues
        SELECT 'linear', 'issue', i.id, i.updated_at, i.title, NULL, i.url,
               i.assignee_id, 'linear', em.person_slug
        FROM stg_linear_issue i
        LEFT JOIN mart_entity_map em ON em.source = 'linear' AND em.external_id = i.assignee_id
        UNION ALL
        -- Granola meetings
        SELECT 'granola', 'meeting', m.id, COALESCE(m.gcal_start_at, m.created_at),
               m.title, m.notes_plain, NULL, NULL, NULL, NULL
        FROM stg_granola_meeting m WHERE m.is_valid
        UNION ALL
        -- Slack messages
        SELECT 'slack', 'message', msg.id, msg.occurred_at,
               '#' || COALESCE(ch.name, msg.channel_id), msg.text, NULL,
               msg.user_id, 'slack', em.person_slug
        FROM stg_slack_message msg
        LEFT JOIN stg_slack_channel ch ON ch.id = msg.channel_id
        LEFT JOIN mart_entity_map em ON em.source = 'slack' AND em.external_id = msg.user_id
        UNION ALL
        -- GDrive files
        SELECT 'gdrive', 'file_modified', f.id, f.modified_at,
               f.name, NULL, f.url,
               f.last_modifier_email, 'email', em.person_slug
        FROM stg_gdrive_file f
        LEFT JOIN mart_entity_map em ON em.source = 'email' AND em.external_id = f.last_modifier_email
    """)
    op.execute(
        "CREATE UNIQUE INDEX idx_mart_timeline_pk "
        "ON mart_activity_timeline (source, kind, source_id)"
    )
    op.execute("CREATE INDEX idx_mart_timeline_at ON mart_activity_timeline (occurred_at)")
    op.execute("CREATE INDEX idx_mart_timeline_actor ON mart_activity_timeline (actor_slug)")

    # ── Person (canonical) ─────────────────────────────────────────────
    op.execute("""
        CREATE VIEW mart_person AS
        SELECT
            p.slug, p.name, p.email, p.role, p.is_direct_report, p.focus_area,
            MAX(CASE WHEN em.source = 'slack' THEN em.external_id END)  AS slack_id,
            MAX(CASE WHEN em.source = 'github' THEN em.external_id END) AS github_login,
            MAX(CASE WHEN em.source = 'linear' THEN em.external_id END) AS linear_id
        FROM people p
        LEFT JOIN entity_mappings em ON em.person_slug = p.slug
        GROUP BY p.slug, p.name, p.email, p.role, p.is_direct_report, p.focus_area
    """)

    # ── Slack channel activity ─────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_slack_channel_activity AS
        SELECT
            c.id        AS channel_id,
            c.name      AS channel_name,
            COUNT(m.id) FILTER (WHERE m.occurred_at > NOW() - INTERVAL '14 days')
                        AS recent_messages,
            MAX(m.occurred_at) AS last_message_at
        FROM stg_slack_channel c
        LEFT JOIN stg_slack_message m ON m.channel_id = c.id
        GROUP BY c.id, c.name
    """)
    op.execute(
        "CREATE UNIQUE INDEX idx_mart_chanact_pk ON mart_slack_channel_activity (channel_id)"
    )

    # ── Person summary ─────────────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_person_summary AS
        SELECT
            p.slug, p.name,
            COUNT(*) FILTER (
                WHERE t.source = 'github' AND t.kind = 'pr'
                  AND t.occurred_at > NOW() - INTERVAL '7 days'
            ) AS prs_7d,
            COUNT(*) FILTER (
                WHERE t.source = 'gcal'
                  AND t.occurred_at > NOW() - INTERVAL '7 days'
            ) AS meetings_7d,
            COUNT(*) FILTER (
                WHERE t.source = 'slack'
                  AND t.occurred_at > NOW() - INTERVAL '7 days'
            ) AS slack_messages_7d,
            COUNT(*) FILTER (
                WHERE t.occurred_at > NOW() - INTERVAL '7 days'
            ) AS total_7d,
            COUNT(*) FILTER (
                WHERE t.occurred_at > NOW() - INTERVAL '30 days'
            ) AS total_30d
        FROM people p
        LEFT JOIN mart_activity_timeline t ON t.actor_slug = p.slug
        GROUP BY p.slug, p.name
    """)
    op.execute("CREATE UNIQUE INDEX idx_mart_perssum_pk ON mart_person_summary (slug)")

    # ── Cross references (URLs in Slack) ───────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_cross_references AS
        SELECT
            m.id         AS message_id,
            c.name       AS channel_name,
            m.occurred_at,
            CASE
                WHEN m.text ~ 'github\.com/[^/]+/[^/]+/pull/' THEN 'github_pr'
                WHEN m.text ~ 'linear\.app/' THEN 'linear'
                WHEN m.text ~ 'docs\.google\.com/' THEN 'gdoc'
                WHEN m.text ~ 'notion\.so/' THEN 'notion'
                ELSE 'other'
            END          AS ref_type,
            (regexp_matches(m.text, '(https?://[^\s>|]+)', 'g'))[1] AS target_url,
            NULL         AS target_title,
            m.url
        FROM stg_slack_message m
        LEFT JOIN stg_slack_channel c ON c.id = m.channel_id
        WHERE m.text ~ 'https?://'
    """)
    op.execute(
        "CREATE INDEX idx_mart_crossref_type ON mart_cross_references (ref_type)"
    )

    # ── Project health ─────────────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_project_health AS
        SELECT
            p.id          AS project_id,
            p.name        AS project_name,
            p.state,
            p.progress,
            COUNT(i.id)   AS total_issues,
            COUNT(i.id) FILTER (WHERE i.completed_at IS NOT NULL) AS done,
            CASE WHEN COUNT(i.id) > 0
                 THEN ROUND(100.0 * COUNT(i.id) FILTER (WHERE i.completed_at IS NOT NULL) / COUNT(i.id), 1)
                 ELSE 0 END AS pct_done,
            CASE
                WHEN p.progress >= 0.8 THEN 'on_track'
                WHEN p.progress >= 0.5 THEN 'at_risk'
                ELSE 'behind'
            END           AS health,
            p.url
        FROM stg_linear_project p
        LEFT JOIN stg_linear_issue i ON i.project_id = p.id
        GROUP BY p.id, p.name, p.state, p.progress, p.url
    """)
    op.execute("CREATE UNIQUE INDEX idx_mart_projhealth_pk ON mart_project_health (project_id)")

    # ── Document index ─────────────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_document_index AS
        SELECT id, name AS title, 'gdrive' AS source_system, url, modified_at
        FROM stg_gdrive_file
        UNION ALL
        SELECT id, title, 'granola', NULL AS url, created_at AS modified_at
        FROM stg_granola_meeting WHERE is_valid
    """)
    op.execute("CREATE UNIQUE INDEX idx_mart_docidx_pk ON mart_document_index (source_system, id)")

    # ── GDoc freshness ─────────────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_gdoc_freshness AS
        SELECT
            f.id, f.name AS title, f.modified_at,
            f.last_modifier_email AS owner_email,
            p.name AS owner_name
        FROM stg_gdrive_file f
        LEFT JOIN entity_mappings em ON em.source = 'email' AND em.external_id = f.last_modifier_email
        LEFT JOIN people p ON p.slug = em.person_slug
        WHERE f.mime_type LIKE 'application/vnd.google-apps.%'
    """)
    op.execute("CREATE UNIQUE INDEX idx_mart_gdocfresh_pk ON mart_gdoc_freshness (id)")

    # ── Customer meeting ───────────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mart_customer_meeting AS
        SELECT
            ev.id,
            ev.title AS event_title,
            ev.start_at,
            ev.organizer_email,
            a.email AS attendee_email,
            SPLIT_PART(a.email, '@', 2) AS attendee_domain,
            gm.id IS NOT NULL AS has_notes,
            gm.title AS notes_title
        FROM stg_gcal_event ev
        LEFT JOIN stg_gcal_attendee a ON a.event_id = ev.id
        LEFT JOIN stg_granola_meeting gm ON gm.gcal_start_at BETWEEN ev.start_at - INTERVAL '15 minutes'
                                                                  AND ev.start_at + INTERVAL '15 minutes'
        WHERE a.email IS NOT NULL
          AND SPLIT_PART(a.email, '@', 2) != 'tempo.xyz'
    """)
    op.execute("CREATE INDEX idx_mart_custmtg_start ON mart_customer_meeting (start_at)")


def downgrade() -> None:
    matviews = [
        "mart_customer_meeting", "mart_gdoc_freshness", "mart_document_index",
        "mart_project_health", "mart_cross_references", "mart_person_summary",
        "mart_slack_channel_activity", "mart_activity_timeline", "mart_slack_thread",
    ]
    views = ["mart_person", "mart_slack_message", "mart_entity_map"]
    for mv in matviews:
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {mv} CASCADE")
    for v in views:
        op.execute(f"DROP VIEW IF EXISTS {v} CASCADE")
