use std::{
    collections::VecDeque,
    env,
    fs::File,
    io::{self, BufRead, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Condvar, Mutex},
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::Result;

#[derive(Clone, Debug)]
pub struct CodeModeExecConfig {
    pub proxy_dir: PathBuf,
    pub env_dir: PathBuf,
    pub max_output_bytes: usize,
    pub default_timeout: Duration,
    pub max_concurrency: usize,
}

#[derive(Debug, Deserialize)]
struct ExecRequest {
    id: String,
    script: String,
    timeout_seconds: Option<u64>,
    max_output_bytes: Option<usize>,
    principal: Option<String>,
}

#[derive(Debug, Serialize)]
struct ExecResponse {
    id: String,
    output: String,
    is_error: bool,
}

#[derive(Debug)]
struct RunOutput {
    output: String,
    is_error: bool,
}

pub fn default_proxy_dir() -> PathBuf {
    home_dir().join(".local/share/centaur-tools/python")
}

pub fn default_env_dir() -> PathBuf {
    home_dir().join(".local/share/centaur-tools/venv")
}

pub fn run_codemode_exec_server(config: CodeModeExecConfig) -> Result<()> {
    let config = Arc::new(config);
    let limiter = Arc::new(ConcurrencyLimiter::new(config.max_concurrency.max(1)));
    let stdout = Arc::new(Mutex::new(io::stdout()));
    let mut workers = VecDeque::new();

    for raw in io::stdin().lock().lines() {
        let raw = raw?;
        let request = match serde_json::from_str::<ExecRequest>(&raw) {
            Ok(request) => request,
            Err(error) => {
                write_response(
                    &stdout,
                    &ExecResponse {
                        id: "parse-error".to_owned(),
                        output: format!("invalid exec request JSON: {error}"),
                        is_error: true,
                    },
                )?;
                continue;
            }
        };

        let permit = limiter.acquire();
        let worker_config = Arc::clone(&config);
        let worker_stdout = Arc::clone(&stdout);
        workers.push_back(thread::spawn(move || {
            let response = handle_request(&worker_config, request);
            if let Err(error) = write_response(&worker_stdout, &response) {
                eprintln!("codemode-exec: failed to write response: {error}");
            }
            drop(permit);
        }));

        while workers.front().is_some_and(thread::JoinHandle::is_finished) {
            let worker = workers.pop_front().expect("front checked");
            let _ = worker.join();
        }
    }

    for worker in workers {
        let _ = worker.join();
    }
    Ok(())
}

fn handle_request(config: &CodeModeExecConfig, request: ExecRequest) -> ExecResponse {
    let principal = request
        .principal
        .clone()
        .or_else(|| env::var("CENTAUR_CODEMODE_PRINCIPAL").ok())
        .unwrap_or_else(|| "unknown-principal".to_owned());
    let timeout = request
        .timeout_seconds
        .map_or(config.default_timeout, Duration::from_secs);
    let max_output_bytes = request.max_output_bytes.unwrap_or(config.max_output_bytes);
    let output = run_script(
        config,
        &request.script,
        timeout,
        max_output_bytes,
        &principal,
    )
    .unwrap_or_else(|error| RunOutput {
        output: format!("error: {error}"),
        is_error: true,
    });
    ExecResponse {
        id: request.id,
        output: output.output,
        is_error: output.is_error,
    }
}

fn run_script(
    config: &CodeModeExecConfig,
    script: &str,
    timeout: Duration,
    max_output_bytes: usize,
    principal: &str,
) -> Result<RunOutput> {
    let id = Uuid::new_v4();
    let script_path = env::temp_dir().join(format!("codemode-{id}.py"));
    let stdout_path = env::temp_dir().join(format!("codemode-{id}.stdout"));
    let stderr_path = env::temp_dir().join(format!("codemode-{id}.stderr"));

    std::fs::write(&script_path, script)?;
    let stdout_file = File::create(&stdout_path)?;
    let stderr_file = File::create(&stderr_path)?;

    let mut command = Command::new(runtime_python(&config.env_dir));
    command
        .arg(&script_path)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file))
        .env("PYTHONPATH", pythonpath(&config.proxy_dir))
        .env(
            "CENTAUR_CODEMODE_EXECUTOR_PID",
            std::process::id().to_string(),
        )
        .env("CENTAUR_CODEMODE_PRINCIPAL", principal);

    let mut child = command.spawn()?;
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = child.try_wait()? {
            let failed = !status.success();
            let output = collect_output(
                &stdout_path,
                &stderr_path,
                max_output_bytes,
                failed.then(|| status.code().unwrap_or(-1)),
            );
            cleanup_paths([&script_path, &stdout_path, &stderr_path]);
            return Ok(RunOutput {
                output,
                is_error: failed,
            });
        }
        if Instant::now() >= deadline {
            break;
        }
        thread::sleep(Duration::from_millis(25));
    }

    let _ = child.kill();
    let _ = child.wait();
    cleanup_paths([&script_path, &stdout_path, &stderr_path]);
    Ok(RunOutput {
        output: format!("error: script timed out after {}s", timeout.as_secs()),
        is_error: true,
    })
}

fn collect_output(
    stdout_path: &Path,
    stderr_path: &Path,
    max_output_bytes: usize,
    exit_code: Option<i32>,
) -> String {
    let mut parts = Vec::new();
    let stdout = std::fs::read_to_string(stdout_path).unwrap_or_default();
    if !stdout.trim().is_empty() {
        parts.push(truncate(stdout.trim_end(), max_output_bytes));
    }
    if let Some(exit_code) = exit_code {
        parts.push(format!("exit code: {exit_code}"));
        let stderr = std::fs::read_to_string(stderr_path).unwrap_or_default();
        if !stderr.trim().is_empty() {
            parts.push(truncate(stderr.trim_end(), 4_000));
        }
    }
    if parts.is_empty() {
        parts.push("(no output)".to_owned());
    }
    parts.join("\n")
}

fn write_response<W: Write>(stdout: &Arc<Mutex<W>>, response: &ExecResponse) -> Result<()> {
    let mut stdout = stdout.lock().expect("stdout lock poisoned");
    serde_json::to_writer(&mut *stdout, response)?;
    stdout.write_all(b"\n")?;
    stdout.flush()?;
    Ok(())
}

fn runtime_python(env_dir: &Path) -> PathBuf {
    let python = env_dir.join("bin/python");
    if python.is_file() {
        python
    } else {
        PathBuf::from("python3")
    }
}

fn pythonpath(proxy_dir: &Path) -> String {
    match env::var("PYTHONPATH") {
        Ok(existing) if !existing.is_empty() => format!("{}:{existing}", proxy_dir.display()),
        _ => proxy_dir.display().to_string(),
    }
}

fn truncate(text: &str, limit: usize) -> String {
    if text.len() <= limit {
        return text.to_owned();
    }
    let mut end = limit;
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    format!(
        "{}\n... [truncated {} bytes]",
        &text[..end],
        text.len() - end
    )
}

fn cleanup_paths<'a>(paths: impl IntoIterator<Item = &'a PathBuf>) {
    for path in paths {
        let _ = std::fs::remove_file(path);
    }
}

fn home_dir() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/tmp"))
}

struct ConcurrencyLimiter {
    inner: Mutex<usize>,
    available: Condvar,
}

struct Permit {
    limiter: Arc<ConcurrencyLimiter>,
}

impl ConcurrencyLimiter {
    fn new(max: usize) -> Self {
        Self {
            inner: Mutex::new(max),
            available: Condvar::new(),
        }
    }

    fn acquire(self: &Arc<Self>) -> Permit {
        let mut slots = self.inner.lock().expect("limiter lock poisoned");
        while *slots == 0 {
            slots = self.available.wait(slots).expect("limiter lock poisoned");
        }
        *slots -= 1;
        Permit {
            limiter: Arc::clone(self),
        }
    }
}

impl Drop for Permit {
    fn drop(&mut self) {
        let mut slots = self.limiter.inner.lock().expect("limiter lock poisoned");
        *slots += 1;
        self.limiter.available.notify_one();
    }
}

#[cfg(test)]
mod tests {
    use super::truncate;

    #[test]
    fn truncate_respects_utf8_boundary() {
        assert_eq!(truncate("abc", 10), "abc");
        assert_eq!(truncate("éé", 3), "é\n... [truncated 2 bytes]");
    }
}
