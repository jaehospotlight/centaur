//! Runtime orchestration for durable Centaur sessions.

mod error;
mod event_stream;
mod runtime;
mod session_io;
mod validation;
mod workload;

pub use error::SessionRuntimeError;
pub use runtime::{ExecuteSessionInput, SandboxRuntime, SessionRuntime};
pub use workload::{CodexAppServerWorkload, SandboxWorkloadMode};

pub const SESSION_OUTPUT_LINE_EVENT: &str = "session.output.line";

const MAX_SESSION_OUTPUT_LINE_BYTES: usize = 1024 * 1024;
