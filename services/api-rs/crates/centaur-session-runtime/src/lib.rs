use std::{
    collections::{HashMap, VecDeque},
    sync::Arc,
    time::Duration,
};

use centaur_sandbox_core::{
    SandboxBackend, SandboxError, SandboxId, SandboxIoGuard, SandboxRead, SandboxSpec,
    SandboxStatus, SandboxWrite,
};
use centaur_sandbox_manager::SandboxManager;
use centaur_session_core::{
    HarnessType, Session, SessionEvent, SessionExecution, SessionMessageInput, ThreadKey,
};
use centaur_session_sqlx::{
    PgSessionStore, SessionEventListener, SessionStoreError, default_metadata,
};
use futures_util::{SinkExt, Stream, StreamExt, stream};
use serde_json::{Value, json};
use thiserror::Error;
use tokio::{
    io,
    sync::Mutex,
    time::{Instant, Interval, MissedTickBehavior, interval_at},
};
use tokio_util::codec::{FramedRead, FramedWrite, LinesCodec, LinesCodecError};
use tracing::warn;

pub const SESSION_OUTPUT_LINE_EVENT: &str = "session.output.line";

const MAX_SESSION_OUTPUT_LINE_BYTES: usize = 1024 * 1024;
const EVENT_STREAM_SAFETY_POLL_INTERVAL: Duration = Duration::from_secs(30);

type SandboxSpecFactory = Arc<dyn Fn(&ThreadKey, &str) -> SandboxSpec + Send + Sync>;
type SessionInputSink = FramedWrite<SandboxWrite, LinesCodec>;

#[derive(Clone)]
pub struct SessionRuntime {
    store: PgSessionStore,
    sandbox_runtime: SandboxRuntime,
    sandbox_pipes: Arc<Mutex<HashMap<String, SessionPipe>>>,
}

#[derive(Clone)]
pub struct SandboxRuntime {
    manager: Arc<SandboxManager>,
    spec_factory: SandboxSpecFactory,
}

#[derive(Clone, Debug)]
pub enum SandboxWorkloadMode {
    MockAppServer {
        image: String,
    },
    CodexAppServer {
        image: String,
        env: Vec<(String, String)>,
    },
}

#[derive(Debug)]
pub struct ExecuteSessionInput {
    pub metadata: Option<Value>,
    pub input_lines: Vec<String>,
    pub idle_timeout_ms: Option<u64>,
    pub max_duration_ms: Option<u64>,
}

#[derive(Clone)]
struct SessionPipe {
    stdin: Arc<Mutex<SessionInputSink>>,
    active_execution: ActiveExecution,
}

#[derive(Clone, Default)]
struct ActiveExecution {
    execution_id: Arc<Mutex<Option<String>>>,
}

struct EventStreamState {
    store: PgSessionStore,
    thread_key: ThreadKey,
    after_event_id: i64,
    pending: VecDeque<SessionEvent>,
    listener: SessionEventListener,
    safety_tick: Interval,
    done: bool,
}

impl SessionRuntime {
    pub fn new(store: PgSessionStore, sandbox_runtime: SandboxRuntime) -> Self {
        Self {
            store,
            sandbox_runtime,
            sandbox_pipes: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub async fn create_or_get_session(
        &self,
        thread_key: &ThreadKey,
        harness_type: &HarnessType,
        metadata: Option<Value>,
    ) -> Result<Session, SessionRuntimeError> {
        Ok(self
            .store
            .create_or_get_session(thread_key, harness_type, default_metadata(metadata))
            .await?)
    }

    pub async fn append_messages(
        &self,
        thread_key: &ThreadKey,
        messages: &[SessionMessageInput],
    ) -> Result<Vec<String>, SessionRuntimeError> {
        if messages.is_empty() {
            return Err(SessionRuntimeError::BadRequest(
                "messages must not be empty".to_owned(),
            ));
        }
        Ok(self.store.append_messages(thread_key, messages).await?)
    }

    pub async fn execute_session(
        &self,
        thread_key: &ThreadKey,
        input: ExecuteSessionInput,
    ) -> Result<SessionExecution, SessionRuntimeError> {
        let session = self.store.get_session(thread_key).await?;
        validate_input_lines(&input.input_lines)?;
        validate_duration_options(&input)?;

        let execution = self
            .store
            .create_execution(thread_key, default_metadata(input.metadata))
            .await?;
        let execution = self
            .store
            .mark_execution_running(&execution.execution_id)
            .await?;
        let sandbox_id = self
            .ensure_session_sandbox(
                thread_key,
                session.sandbox_id.as_deref(),
                &execution.execution_id,
            )
            .await?;

        self.store
            .append_event(
                thread_key,
                Some(&execution.execution_id),
                "session.execution_started",
                json!({
                    "execution_id": execution.execution_id,
                    "thread_key": thread_key.as_str(),
                    "input_line_count": input.input_lines.len(),
                }),
            )
            .await?;

        let write_result = match self.ensure_session_pipe(thread_key, &sandbox_id).await {
            Ok(pipe) => {
                pipe.active_execution
                    .set(Some(execution.execution_id.clone()))
                    .await;
                write_input_lines(&pipe, &input.input_lines).await
            }
            Err(error) => Err(error),
        };

        match write_result {
            Ok(()) => {}
            Err(error) => {
                self.clear_active_execution(&sandbox_id, &execution.execution_id)
                    .await;
                let error_message = error.to_string();
                let _ = self
                    .store
                    .append_event(
                        thread_key,
                        Some(&execution.execution_id),
                        "session.execution_failed",
                        json!({
                            "execution_id": execution.execution_id,
                            "thread_key": thread_key.as_str(),
                            "error": error_message,
                        }),
                    )
                    .await;
                let _ = self
                    .store
                    .fail_execution(&execution.execution_id, &error_message)
                    .await;
                return Err(error);
            }
        }

        Ok(execution)
    }

    pub async fn stream_events(
        &self,
        thread_key: &ThreadKey,
        after_event_id: i64,
    ) -> Result<
        impl Stream<Item = Result<SessionEvent, SessionRuntimeError>> + use<>,
        SessionRuntimeError,
    > {
        let session = self.store.get_session(thread_key).await?;
        if let Some(sandbox_id) = session.sandbox_id.as_deref() {
            self.ensure_session_pipe(thread_key, sandbox_id).await?;
        }

        let listener = self.store.listen_session_events().await?;

        Ok(session_event_stream(
            self.store.clone(),
            thread_key.clone(),
            after_event_id,
            listener,
        ))
    }

    async fn ensure_session_sandbox(
        &self,
        thread_key: &ThreadKey,
        existing_sandbox_id: Option<&str>,
        execution_id: &str,
    ) -> Result<String, SessionRuntimeError> {
        if let Some(sandbox_id) = existing_sandbox_id {
            let id = SandboxId::new(sandbox_id);
            match self.sandbox_runtime.manager.status(&id).await {
                Ok(SandboxStatus::Running | SandboxStatus::Created) => {
                    return Ok(sandbox_id.to_owned());
                }
                Ok(_) | Err(SandboxError::NotFound(_)) => {}
                Err(error) => return Err(SessionRuntimeError::Sandbox(error)),
            }
        }

        let spec = (self.sandbox_runtime.spec_factory)(thread_key, execution_id);
        let handle = self.sandbox_runtime.manager.create_running(spec).await?;
        self.store
            .update_sandbox_id(thread_key, Some(handle.id.as_str()))
            .await?;
        Ok(handle.id.into_string())
    }

    async fn ensure_session_pipe(
        &self,
        thread_key: &ThreadKey,
        sandbox_id: &str,
    ) -> Result<SessionPipe, SessionRuntimeError> {
        if let Some(pipe) = self.sandbox_pipes.lock().await.get(sandbox_id).cloned() {
            return Ok(pipe);
        }

        let io = self
            .sandbox_runtime
            .manager
            .open_io(&SandboxId::new(sandbox_id))
            .await?
            .into_parts();
        let pipe = SessionPipe {
            stdin: Arc::new(Mutex::new(FramedWrite::new(
                io.stdin,
                LinesCodec::new_with_max_length(MAX_SESSION_OUTPUT_LINE_BYTES),
            ))),
            active_execution: ActiveExecution::default(),
        };

        self.sandbox_pipes
            .lock()
            .await
            .insert(sandbox_id.to_owned(), pipe.clone());
        let store = self.store.clone();
        let thread_key = thread_key.clone();
        let pump_key = sandbox_id.to_owned();
        let sandbox_pipes = self.sandbox_pipes.clone();
        let stdout = io.stdout;
        let stderr = io.stderr;
        let guard = io.guard;
        let stderr_key = pump_key.clone();
        let active_execution = pipe.active_execution.clone();

        tokio::spawn(async move {
            let result = run_stdout_pump(
                store.clone(),
                thread_key.clone(),
                &pump_key,
                stdout,
                guard,
                active_execution.clone(),
            )
            .await;
            if let Err(error) = result {
                warn!(%pump_key, %error, "session stdout pump failed");
                let execution_id = active_execution.current().await;
                let _ = store
                    .append_event(
                        &thread_key,
                        execution_id.as_deref(),
                        "session.stdout_pump_failed",
                        json!({
                            "sandbox_id": pump_key.as_str(),
                            "error": error.to_string(),
                        }),
                    )
                    .await;
            }
            sandbox_pipes.lock().await.remove(&pump_key);
        });

        tokio::spawn(async move {
            if let Err(error) = drain_stderr(stderr).await {
                warn!(%stderr_key, %error, "session stderr drain failed");
            }
        });

        Ok(pipe)
    }

    async fn clear_active_execution(&self, sandbox_id: &str, execution_id: &str) {
        let pipe = self.sandbox_pipes.lock().await.get(sandbox_id).cloned();
        if let Some(pipe) = pipe {
            pipe.active_execution.clear_if_current(execution_id).await;
        }
    }
}

impl ActiveExecution {
    async fn set(&self, execution_id: Option<String>) {
        *self.execution_id.lock().await = execution_id;
    }

    async fn current(&self) -> Option<String> {
        self.execution_id.lock().await.clone()
    }

    async fn clear_if_current(&self, execution_id: &str) {
        let mut current = self.execution_id.lock().await;
        if current.as_deref() == Some(execution_id) {
            *current = None;
        }
    }
}

impl SandboxRuntime {
    pub fn backend(backend: Arc<dyn SandboxBackend>, spec: SandboxSpec) -> Self {
        let spec_factory = move |_thread_key: &ThreadKey, _execution_id: &str| spec.clone();
        Self::backend_with_spec_factory(backend, spec_factory)
    }

    pub fn backend_with_workload(
        backend: Arc<dyn SandboxBackend>,
        workload: SandboxWorkloadMode,
    ) -> Self {
        Self::backend_with_spec_factory(backend, move |thread_key, _execution_id| {
            workload.spec(thread_key)
        })
    }

    pub fn backend_with_spec_factory<F>(backend: Arc<dyn SandboxBackend>, spec_factory: F) -> Self
    where
        F: Fn(&ThreadKey, &str) -> SandboxSpec + Send + Sync + 'static,
    {
        Self {
            manager: Arc::new(SandboxManager::new(backend)),
            spec_factory: Arc::new(spec_factory),
        }
    }
}

impl SandboxWorkloadMode {
    pub fn mock_app_server(image: impl Into<String>) -> Self {
        Self::MockAppServer {
            image: image.into(),
        }
    }

    pub fn codex_app_server(
        image: impl Into<String>,
        env: impl IntoIterator<Item = (String, String)>,
    ) -> Self {
        Self::CodexAppServer {
            image: image.into(),
            env: env.into_iter().collect(),
        }
    }

    fn spec(&self, thread_key: &ThreadKey) -> SandboxSpec {
        match self {
            Self::MockAppServer { image } => SandboxSpec::new(image)
                .command(["/bin/sh", "-lc"])
                .args([mock_app_server_script()]),
            Self::CodexAppServer { image, env } => {
                let mut spec =
                    SandboxSpec::new(image).env("CENTAUR_THREAD_KEY", thread_key.as_str());
                for (name, value) in env {
                    spec = spec.env(name.clone(), value.clone());
                }
                spec
            }
        }
    }
}

fn mock_app_server_script() -> &'static str {
    r#"while IFS= read -r line; do
printf '%s\n' '{"type":"system","subtype":"wrapper_heartbeat","phase":"startup"}'
sleep 0.2
printf '%s\n' '{"type":"system","subtype":"wrapper_heartbeat","phase":"app_server_started"}'
sleep 0.2
printf '%s\n' '{"type":"thread.started","thread_id":"mock-codex-thread"}'
sleep 0.2
turn_index="${turn_index:-0}"
turn_index=$((turn_index + 1))
  turn_id="mock-turn-$turn_index"
  printf '{"type":"turn.started","turn_id":"%s"}\n' "$turn_id"
  sleep 0.2
  printf '{"type":"item.agentMessage.delta","turnId":"%s","session_id":"mock-codex-thread","delta":"PONG %s"}\n' "$turn_id" "$turn_index"
  sleep 0.2
  printf '{"type":"turn.completed","turn":{"id":"%s"},"usage":{"input_tokens":0,"output_tokens":1}}\n' "$turn_id"
  sleep 0.2
done"#
}

fn session_event_stream(
    store: PgSessionStore,
    thread_key: ThreadKey,
    after_event_id: i64,
    listener: SessionEventListener,
) -> impl Stream<Item = Result<SessionEvent, SessionRuntimeError>> {
    stream::unfold(
        EventStreamState {
            store,
            thread_key,
            after_event_id,
            pending: VecDeque::new(),
            listener,
            safety_tick: {
                let mut tick = interval_at(
                    Instant::now() + EVENT_STREAM_SAFETY_POLL_INTERVAL,
                    EVENT_STREAM_SAFETY_POLL_INTERVAL,
                );
                tick.set_missed_tick_behavior(MissedTickBehavior::Delay);
                tick
            },
            done: false,
        },
        |mut state| async move {
            loop {
                if let Some(event) = state.pending.pop_front() {
                    state.after_event_id = event.event_id;
                    return Some((Ok(event), state));
                }
                if state.done {
                    return None;
                }
                match state
                    .store
                    .list_events_after(&state.thread_key, state.after_event_id, 100)
                    .await
                {
                    Ok(events) if events.is_empty() => loop {
                        tokio::select! {
                            notification = state.listener.recv() => {
                                match notification {
                                    Ok(notification)
                                        if notification.thread_key == state.thread_key.as_str()
                                            && notification.event_id > state.after_event_id =>
                                    {
                                        break;
                                    }
                                    Ok(_) => {}
                                    Err(error) => {
                                        state.done = true;
                                        return Some((Err(SessionRuntimeError::Store(error)), state));
                                    }
                                }
                            }
                            _ = state.safety_tick.tick() => break,
                        }
                    },
                    Ok(events) => state.pending = events.into(),
                    Err(error) => {
                        state.done = true;
                        return Some((Err(SessionRuntimeError::Store(error)), state));
                    }
                }
            }
        },
    )
}

async fn run_stdout_pump(
    store: PgSessionStore,
    thread_key: ThreadKey,
    sandbox_id: &str,
    stdout: SandboxRead,
    _guard: SandboxIoGuard,
    active_execution: ActiveExecution,
) -> Result<(), SessionRuntimeError> {
    let mut stdout = FramedRead::new(
        stdout,
        LinesCodec::new_with_max_length(MAX_SESSION_OUTPUT_LINE_BYTES),
    );
    while let Some(line) = stdout.next().await {
        let line = line.map_err(codec_error_to_runtime)?;
        let execution_id = active_execution.current().await;
        append_output_line(&store, &thread_key, execution_id.as_deref(), &line).await?;
        if let (Some(execution_id), Some(terminal)) =
            (execution_id.as_deref(), terminal_output_line(&line))
        {
            finish_execution_from_output(&store, &thread_key, execution_id, terminal).await?;
            active_execution.clear_if_current(execution_id).await;
        }
    }
    let execution_id = active_execution.current().await;
    if let Some(execution_id) = execution_id.as_deref() {
        let error = "sandbox stdout closed before terminal output";
        store
            .append_event(
                &thread_key,
                Some(execution_id),
                "session.execution_failed",
                json!({
                    "execution_id": execution_id,
                    "thread_key": thread_key.as_str(),
                    "error": error,
                }),
            )
            .await?;
        store.fail_execution(execution_id, error).await?;
        active_execution.clear_if_current(execution_id).await;
    }
    store
        .append_event(
            &thread_key,
            execution_id.as_deref(),
            "session.stdout_eof",
            json!({
                "sandbox_id": sandbox_id,
            }),
        )
        .await?;
    Ok(())
}

async fn finish_execution_from_output(
    store: &PgSessionStore,
    thread_key: &ThreadKey,
    execution_id: &str,
    terminal: TerminalOutput,
) -> Result<(), SessionRuntimeError> {
    match terminal {
        TerminalOutput::Completed => {
            store
                .append_event(
                    thread_key,
                    Some(execution_id),
                    "session.execution_completed",
                    json!({
                        "execution_id": execution_id,
                        "thread_key": thread_key.as_str(),
                        "completion_reason": "terminal_output",
                    }),
                )
                .await?;
            store.complete_execution(execution_id).await?;
        }
        TerminalOutput::Failed { error } => {
            store
                .append_event(
                    thread_key,
                    Some(execution_id),
                    "session.execution_failed",
                    json!({
                        "execution_id": execution_id,
                        "thread_key": thread_key.as_str(),
                        "error": error,
                    }),
                )
                .await?;
            store.fail_execution(execution_id, &error).await?;
        }
    }
    Ok(())
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum TerminalOutput {
    Completed,
    Failed { error: String },
}

fn terminal_output_line(line: &str) -> Option<TerminalOutput> {
    let payload = serde_json::from_str::<Value>(line).ok()?;
    let event_type = payload
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let method = payload
        .get("method")
        .and_then(Value::as_str)
        .unwrap_or_default();

    match (event_type, method) {
        ("turn.completed" | "turn.done", _) | ("", "turn/completed") => {
            Some(TerminalOutput::Completed)
        }
        ("result", _) if payload.get("subtype").and_then(Value::as_str) != Some("error") => {
            Some(TerminalOutput::Completed)
        }
        ("turn.failed" | "error", _) | ("", "turn/failed" | "error") => {
            Some(TerminalOutput::Failed {
                error: terminal_error_message(&payload),
            })
        }
        ("result", _) => Some(TerminalOutput::Failed {
            error: terminal_error_message(&payload),
        }),
        _ => None,
    }
}

fn terminal_error_message(payload: &Value) -> String {
    if let Some(params) = payload.get("params")
        && let Some(message) = terminal_error_message_value(params)
    {
        return message;
    }
    terminal_error_message_value(payload).unwrap_or_else(|| "execution failed".to_owned())
}

fn terminal_error_message_value(payload: &Value) -> Option<String> {
    for key in ["error", "message", "result"] {
        match payload.get(key) {
            Some(Value::String(value)) if !value.trim().is_empty() => return Some(value.clone()),
            Some(value) if value.is_object() || value.is_array() => return Some(value.to_string()),
            _ => {}
        }
    }
    None
}

async fn drain_stderr(mut stderr: SandboxRead) -> Result<(), SessionRuntimeError> {
    io::copy(&mut stderr, &mut io::sink())
        .await
        .map_err(|err| {
            SessionRuntimeError::Sandbox(SandboxError::Io(format!("drain stderr: {err}")))
        })?;
    Ok(())
}

async fn write_input_lines(
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

fn validate_input_lines(lines: &[String]) -> Result<(), SessionRuntimeError> {
    for (index, line) in lines.iter().enumerate() {
        if line.contains('\n') || line.contains('\r') {
            return Err(SessionRuntimeError::BadRequest(format!(
                "input_lines[{index}] must be one line"
            )));
        }
    }
    Ok(())
}

fn codec_error_to_runtime(error: LinesCodecError) -> SessionRuntimeError {
    SessionRuntimeError::Sandbox(SandboxError::Io(error.to_string()))
}

fn validate_duration_options(input: &ExecuteSessionInput) -> Result<(), SessionRuntimeError> {
    let idle_timeout = input
        .idle_timeout_ms
        .map(nonzero_duration_millis)
        .transpose()?;
    let max_duration = input
        .max_duration_ms
        .map(nonzero_duration_millis)
        .transpose()?;

    if let (Some(idle_timeout), Some(max_duration)) = (idle_timeout, max_duration)
        && idle_timeout > max_duration
    {
        return Err(SessionRuntimeError::BadRequest(
            "idle_timeout_ms must be less than or equal to max_duration_ms".to_owned(),
        ));
    }

    Ok(())
}

fn nonzero_duration_millis(value: u64) -> Result<Duration, SessionRuntimeError> {
    if value == 0 {
        return Err(SessionRuntimeError::BadRequest(
            "duration values must be greater than zero".to_owned(),
        ));
    }
    Ok(Duration::from_millis(value))
}

#[derive(Debug, Error)]
pub enum SessionRuntimeError {
    #[error("{0}")]
    BadRequest(String),
    #[error(transparent)]
    Store(#[from] SessionStoreError),
    #[error(transparent)]
    Sandbox(#[from] SandboxError),
}

#[cfg(test)]
mod tests {
    use super::{TerminalOutput, terminal_output_line};

    #[test]
    fn terminal_output_line_matches_codex_type_events() {
        assert_eq!(
            terminal_output_line(r#"{"type":"turn.completed","turn":{"id":"turn-1"}}"#),
            Some(TerminalOutput::Completed)
        );
        assert_eq!(
            terminal_output_line(r#"{"type":"turn.done","result":"done"}"#),
            Some(TerminalOutput::Completed)
        );
    }

    #[test]
    fn terminal_output_line_matches_app_server_methods() {
        assert_eq!(
            terminal_output_line(
                r#"{"method":"turn/completed","params":{"turn":{"id":"turn-1"}}}"#
            ),
            Some(TerminalOutput::Completed)
        );
    }

    #[test]
    fn terminal_output_line_extracts_failures() {
        assert_eq!(
            terminal_output_line(r#"{"type":"turn.failed","error":"model stopped"}"#),
            Some(TerminalOutput::Failed {
                error: "model stopped".to_owned()
            })
        );
        assert_eq!(
            terminal_output_line(r#"{"method":"error","params":{"message":"boom"}}"#),
            Some(TerminalOutput::Failed {
                error: "boom".to_owned()
            })
        );
    }

    #[test]
    fn terminal_output_line_ignores_non_terminal_output() {
        assert_eq!(
            terminal_output_line(
                r#"{"type":"item.agentMessage.delta","itemId":"msg-1","delta":"hello"}"#
            ),
            None
        );
        assert_eq!(terminal_output_line("not json"), None);
    }
}
