use centaur_sandbox_core::{HarnessAuthMode, HarnessAuthModes};
use clap::{Args as ClapArgs, ValueEnum};

#[derive(Debug, ClapArgs)]
pub(super) struct HarnessAuthArgs {
    #[arg(long = "codex-auth-mode")]
    codex: Option<HarnessAuthModeArg>,
    #[arg(long = "claude-code-auth-mode")]
    claude_code: Option<HarnessAuthModeArg>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum HarnessAuthModeArg {
    #[value(name = "api_key")]
    ApiKey,
    #[value(name = "access_token")]
    AccessToken,
}

impl From<HarnessAuthModeArg> for HarnessAuthMode {
    fn from(value: HarnessAuthModeArg) -> Self {
        match value {
            HarnessAuthModeArg::ApiKey => Self::ApiKey,
            HarnessAuthModeArg::AccessToken => Self::AccessToken,
        }
    }
}

impl HarnessAuthArgs {
    pub(super) fn modes(&self) -> HarnessAuthModes {
        HarnessAuthModes::new(self.codex.map(Into::into), self.claude_code.map(Into::into))
    }
}
