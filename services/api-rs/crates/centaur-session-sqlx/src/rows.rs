use std::str::FromStr;

use centaur_session_core::{Session, SessionEvent, SessionExecution, SessionMessage};
use serde_json::Value;
use sqlx::FromRow;
use time::OffsetDateTime;

use crate::SessionStoreError;

#[derive(Debug, FromRow)]
pub(crate) struct SessionRow {
    pub(crate) thread_key: String,
    pub(crate) sandbox_id: Option<String>,
    pub(crate) harness_type: String,
    pub(crate) harness_thread_id: Option<String>,
    pub(crate) status: String,
    pub(crate) created_at: OffsetDateTime,
    pub(crate) updated_at: OffsetDateTime,
}

impl TryFrom<SessionRow> for Session {
    type Error = SessionStoreError;

    fn try_from(row: SessionRow) -> Result<Self, Self::Error> {
        Ok(Self {
            thread_key: parse_persisted(row.thread_key)?,
            sandbox_id: row.sandbox_id,
            harness_type: parse_persisted(row.harness_type)?,
            harness_thread_id: row.harness_thread_id,
            status: parse_persisted(row.status)?,
            created_at: row.created_at,
            updated_at: row.updated_at,
        })
    }
}

#[derive(Debug, FromRow)]
pub(crate) struct SessionMessageRow {
    pub(crate) message_id: String,
    pub(crate) thread_key: String,
    pub(crate) role: String,
    pub(crate) parts: Value,
    pub(crate) metadata: Value,
    pub(crate) created_at: OffsetDateTime,
}

impl TryFrom<SessionMessageRow> for SessionMessage {
    type Error = SessionStoreError;

    fn try_from(row: SessionMessageRow) -> Result<Self, Self::Error> {
        let parts = match row.parts {
            Value::Array(parts) => parts,
            other => vec![other],
        };
        Ok(Self {
            message_id: row.message_id,
            thread_key: parse_persisted(row.thread_key)?,
            role: parse_persisted(row.role)?,
            parts,
            metadata: row.metadata,
            created_at: row.created_at,
        })
    }
}

#[derive(Debug, FromRow)]
pub(crate) struct SessionExecutionRow {
    pub(crate) execution_id: String,
    pub(crate) thread_key: String,
    pub(crate) status: String,
    pub(crate) metadata: Value,
    pub(crate) error: Option<String>,
    pub(crate) created_at: OffsetDateTime,
    pub(crate) updated_at: OffsetDateTime,
    pub(crate) started_at: Option<OffsetDateTime>,
    pub(crate) completed_at: Option<OffsetDateTime>,
}

impl TryFrom<SessionExecutionRow> for SessionExecution {
    type Error = SessionStoreError;

    fn try_from(row: SessionExecutionRow) -> Result<Self, Self::Error> {
        Ok(Self {
            execution_id: row.execution_id,
            thread_key: parse_persisted(row.thread_key)?,
            status: parse_persisted(row.status)?,
            metadata: row.metadata,
            error: row.error,
            created_at: row.created_at,
            updated_at: row.updated_at,
            started_at: row.started_at,
            completed_at: row.completed_at,
        })
    }
}

#[derive(Debug, FromRow)]
pub(crate) struct SessionEventRow {
    pub(crate) event_id: i64,
    pub(crate) thread_key: String,
    pub(crate) execution_id: Option<String>,
    pub(crate) event_type: String,
    pub(crate) payload: Value,
    pub(crate) created_at: OffsetDateTime,
}

impl TryFrom<SessionEventRow> for SessionEvent {
    type Error = SessionStoreError;

    fn try_from(row: SessionEventRow) -> Result<Self, Self::Error> {
        Ok(Self {
            event_id: row.event_id,
            thread_key: parse_persisted(row.thread_key)?,
            execution_id: row.execution_id,
            event_type: row.event_type,
            payload: row.payload,
            created_at: row.created_at,
        })
    }
}

fn parse_persisted<T>(value: String) -> Result<T, SessionStoreError>
where
    T: FromStr,
    T::Err: std::fmt::Display,
{
    value
        .parse()
        .map_err(|err: T::Err| SessionStoreError::InvalidPersistedValue(err.to_string()))
}
