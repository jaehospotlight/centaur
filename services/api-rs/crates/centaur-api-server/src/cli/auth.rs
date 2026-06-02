use centaur_sandbox_core::{HarnessAuthMode, HarnessAuthModes};
use clap::Args as ClapArgs;

#[derive(Debug, ClapArgs)]
pub(super) struct HarnessAuthArgs {
    #[arg(long = "codex-auth-mode")]
    codex: Option<HarnessAuthMode>,
    #[arg(long = "claude-code-auth-mode")]
    claude_code: Option<HarnessAuthMode>,
}

impl HarnessAuthArgs {
    pub(super) fn modes(&self) -> HarnessAuthModes {
        HarnessAuthModes {
            codex: self.codex,
            claude_code: self.claude_code,
        }
    }
}
