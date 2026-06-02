use std::sync::Arc;

use centaur_sandbox_core::{SandboxError, SandboxIoGuard, SandboxRead, SandboxWrite};
use centaur_session_core::ThreadKey;
use centaur_session_sqlx::PgSessionStore;
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio::{io, sync::Mutex};
use tokio_util::codec::{FramedRead, FramedWrite, LinesCodec, LinesCodecError};

use crate::{MAX_SESSION_OUTPUT_LINE_BYTES, SESSION_OUTPUT_LINE_EVENT, SessionRuntimeError};

type SessionInputSink = FramedWrite<SandboxWrite, LinesCodec>;

#[derive(Clone)]
pub(crate) struct SessionPipe {
    stdin: Arc<Mutex<SessionInputSink>>,
}

impl SessionPipe {
    pub(crate) fn new(stdin: SandboxWrite) -> Self {
        Self {
            stdin: Arc::new(Mutex::new(FramedWrite::new(
                stdin,
                LinesCodec::new_with_max_length(MAX_SESSION_OUTPUT_LINE_BYTES),
            ))),
        }
    }
}

pub(crate) async fn run_stdout_pump(
    store: PgSessionStore,
    thread_key: ThreadKey,
    sandbox_id: &str,
    stdout: SandboxRead,
    _guard: SandboxIoGuard,
) -> Result<(), SessionRuntimeError> {
    let mut stdout = FramedRead::new(
        stdout,
        LinesCodec::new_with_max_length(MAX_SESSION_OUTPUT_LINE_BYTES),
    );
    while let Some(line) = stdout.next().await {
        let line = line.map_err(codec_error_to_runtime)?;
        append_output_line(&store, &thread_key, None, &line).await?;
    }
    store
        .append_event(
            &thread_key,
            None,
            "session.stdout_eof",
            json!({
                "sandbox_id": sandbox_id,
            }),
        )
        .await?;
    Ok(())
}

pub(crate) async fn drain_stderr(mut stderr: SandboxRead) -> Result<(), SessionRuntimeError> {
    io::copy(&mut stderr, &mut io::sink())
        .await
        .map_err(|err| {
            SessionRuntimeError::Sandbox(SandboxError::Io(format!("drain stderr: {err}")))
        })?;
    Ok(())
}

pub(crate) async fn write_input_lines(
    pipe: &SessionPipe,
    input_lines: &[String],
) -> Result<(), SessionRuntimeError> {
    let mut stdin = pipe.stdin.lock().await;
    for line in input_lines {
        stdin.send(line).await.map_err(codec_error_to_runtime)?;
    }
    Ok(())
}

async fn append_output_line(
    store: &PgSessionStore,
    thread_key: &ThreadKey,
    execution_id: Option<&str>,
    line: &str,
) -> Result<(), SessionRuntimeError> {
    store
        .append_event(
            thread_key,
            execution_id,
            SESSION_OUTPUT_LINE_EVENT,
            Value::String(line.to_owned()),
        )
        .await?;
    Ok(())
}

fn codec_error_to_runtime(error: LinesCodecError) -> SessionRuntimeError {
    SessionRuntimeError::Sandbox(SandboxError::Io(error.to_string()))
}
