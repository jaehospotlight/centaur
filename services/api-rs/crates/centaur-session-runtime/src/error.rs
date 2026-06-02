use centaur_sandbox_core::SandboxError;
use centaur_session_sqlx::SessionStoreError;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SessionRuntimeError {
    #[error("{0}")]
    BadRequest(String),
    #[error(transparent)]
    Store(#[from] SessionStoreError),
    #[error(transparent)]
    Sandbox(#[from] SandboxError),
}
