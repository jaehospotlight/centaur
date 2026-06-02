use thiserror::Error;

#[derive(Debug, Error)]
pub enum SessionStoreError {
    #[error("session not found for thread_key {thread_key}")]
    NotFound { thread_key: String },
    #[error(
        "session {thread_key} already exists with harness_type {existing}, requested {requested}"
    )]
    HarnessConflict {
        thread_key: String,
        existing: String,
        requested: String,
    },
    #[error("invalid persisted value: {0}")]
    InvalidPersistedValue(String),
    #[error("invalid notification payload on {channel}: {payload}: {error}")]
    InvalidNotification {
        channel: String,
        payload: String,
        error: serde_json::Error,
    },
    #[error(transparent)]
    Sqlx(#[from] sqlx::Error),
    #[error(transparent)]
    Migrate(#[from] sqlx::migrate::MigrateError),
}
