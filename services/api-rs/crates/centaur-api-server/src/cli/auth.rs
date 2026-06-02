use std::collections::BTreeMap;

use centaur_session_runtime::AppServerAuthMode;
use clap::{Args as ClapArgs, ValueEnum};

#[derive(Debug, ClapArgs)]
pub(super) struct HarnessAuthArgs {
    #[arg(long = "codex-auth-mode", env = "CODEX_AUTH_MODE")]
    codex: Option<HarnessAuthMode>,
    #[arg(long = "claude-code-auth-mode", env = "CLAUDE_CODE_AUTH_MODE")]
    claude_code: Option<HarnessAuthMode>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum HarnessAuthMode {
    #[value(name = "api_key")]
    ApiKey,
    #[value(name = "access_token")]
    AccessToken,
}

impl From<HarnessAuthMode> for AppServerAuthMode {
    fn from(value: HarnessAuthMode) -> Self {
        match value {
            HarnessAuthMode::ApiKey => Self::ApiKey,
            HarnessAuthMode::AccessToken => Self::AccessToken,
        }
    }
}

impl HarnessAuthMode {
    fn proxy_value(self) -> &'static str {
        match self {
            Self::ApiKey => "api_key",
            Self::AccessToken => "access_token",
        }
    }
}

impl HarnessAuthArgs {
    pub(super) fn codex_auth_mode(&self) -> Option<AppServerAuthMode> {
        self.codex.map(Into::into)
    }

    pub(super) fn claude_code_auth_mode(&self) -> Option<AppServerAuthMode> {
        self.claude_code.map(Into::into)
    }

    pub(super) fn proxy_modes(&self) -> BTreeMap<String, String> {
        [
            self.codex
                .map(|mode| ("codex".to_owned(), mode.proxy_value().to_owned())),
            self.claude_code
                .map(|mode| ("claude-code".to_owned(), mode.proxy_value().to_owned())),
        ]
        .into_iter()
        .flatten()
        .collect()
    }
}
