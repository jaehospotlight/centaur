use clap::{Parser, Subcommand, ValueEnum};
use harness_server::{
    CodeModeExecConfig, HarnessKind, Result, default_env_dir, default_proxy_dir, run_blocks_server,
    run_codemode_exec_server, run_harness_server, run_validate_agent_deltas, run_validate_jsonrpc,
};
use std::{path::PathBuf, time::Duration};

#[derive(Debug, Parser)]
#[command(
    version,
    about = "Serve harness CLIs through the Codex App Server V2 protocol."
)]
struct Cli {
    #[command(subcommand)]
    command: Option<CliCommand>,
}

#[derive(Debug, Subcommand)]
#[command(rename_all = "kebab-case")]
enum CliCommand {
    Codex(HarnessCommand),
    #[command(alias = "claude")]
    ClaudeCode(HarnessCommand),
    Amp(HarnessCommand),
    CodemodeExec(CodeModeExecCommand),
    ValidateJsonrpc,
    ValidateAgentDeltas,
}

#[derive(Debug, Parser)]
struct HarnessCommand {
    #[arg(long, value_enum, default_value_t = ServerMode::Blocks)]
    mode: ServerMode,
}

#[derive(Debug, Parser)]
struct CodeModeExecCommand {
    #[arg(long, default_value_os_t = default_proxy_dir())]
    proxy_dir: PathBuf,
    #[arg(long, default_value_os_t = default_env_dir())]
    env_dir: PathBuf,
    #[arg(long, default_value_t = 10_000)]
    max_output_bytes: usize,
    #[arg(long, default_value_t = 120)]
    default_timeout_seconds: u64,
    #[arg(long, default_value_t = 8)]
    max_concurrency: usize,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum ServerMode {
    Blocks,
    Jsonrpc,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("harness-server: {error:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    match Cli::parse()
        .command
        .unwrap_or(CliCommand::Codex(HarnessCommand {
            mode: ServerMode::Blocks,
        })) {
        CliCommand::Codex(command) => run_mode(HarnessKind::Codex, command.mode),
        CliCommand::ClaudeCode(command) => run_mode(HarnessKind::ClaudeCode, command.mode),
        CliCommand::Amp(command) => run_mode(HarnessKind::Amp, command.mode),
        CliCommand::CodemodeExec(command) => run_codemode_exec_server(CodeModeExecConfig {
            proxy_dir: command.proxy_dir,
            env_dir: command.env_dir,
            max_output_bytes: command.max_output_bytes,
            default_timeout: Duration::from_secs(command.default_timeout_seconds),
            max_concurrency: command.max_concurrency,
        }),
        CliCommand::ValidateJsonrpc => run_validate_jsonrpc(),
        CliCommand::ValidateAgentDeltas => run_validate_agent_deltas(),
    }
}

fn run_mode(kind: HarnessKind, mode: ServerMode) -> Result<()> {
    match mode {
        ServerMode::Blocks => run_blocks_server(kind),
        ServerMode::Jsonrpc => run_harness_server(kind),
    }
}
