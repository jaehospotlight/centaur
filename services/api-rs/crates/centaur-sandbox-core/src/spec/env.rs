use std::str::FromStr;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct EnvVar {
    pub name: String,
    pub value: String,
}

impl EnvVar {
    pub fn new(name: impl Into<String>, value: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            value: value.into(),
        }
    }
}

impl FromStr for EnvVar {
    type Err = String;

    fn from_str(raw: &str) -> Result<Self, Self::Err> {
        let (name, value) = raw
            .split_once('=')
            .ok_or_else(|| "env var must be NAME=VALUE".to_owned())?;
        let name = name.trim();
        if name.is_empty() {
            return Err("env var name must not be empty".to_owned());
        }
        Ok(Self::new(name, value))
    }
}
