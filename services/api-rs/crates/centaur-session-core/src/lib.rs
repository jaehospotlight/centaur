//! Durable session control-plane types.
//!
//! A session is the public control-plane object for one ongoing agent
//! conversation. `thread_key` is the canonical identifier.

mod metadata;
mod session;
mod thread_key;

pub use metadata::empty_object;
pub use session::{
    ExecutionStatus, HarnessType, MessageRole, Session, SessionEvent, SessionExecution,
    SessionMessage, SessionMessageInput, SessionStatus,
};
pub use thread_key::{MAX_THREAD_KEY_BYTES, ThreadKey, ThreadKeyError};
