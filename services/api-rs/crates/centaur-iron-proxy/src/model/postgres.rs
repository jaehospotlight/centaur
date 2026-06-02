use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_yaml::Value;

use super::values::{resolve_placeholder_source_values, resolve_source_values};
use crate::{Result, SourcePolicy};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct PostgresListener {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub listen: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub upstream: Option<PostgresUpstream>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub client: Option<PostgresClient>,
    #[serde(default, skip_serializing)]
    pub sandbox_env: Option<SandboxEnv>,
    #[serde(default, flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl PostgresListener {
    pub(crate) fn resolve_sources(&mut self, source_policy: &SourcePolicy) -> Result<()> {
        if let Some(upstream) = &mut self.upstream {
            upstream.resolve_sources(source_policy)?;
        }
        if let Some(client) = &mut self.client {
            client.resolve_sources(source_policy)?;
        }
        resolve_source_values(self.extra.values_mut(), source_policy)
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct PostgresUpstream {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dsn: Option<Value>,
    #[serde(default, flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl PostgresUpstream {
    fn resolve_sources(&mut self, source_policy: &SourcePolicy) -> Result<()> {
        if let Some(dsn) = &mut self.dsn {
            resolve_placeholder_source_values(dsn, source_policy)?;
        }
        resolve_source_values(self.extra.values_mut(), source_policy)
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct PostgresClient {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub password_env: Option<String>,
    #[serde(default, flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl PostgresClient {
    fn resolve_sources(&mut self, source_policy: &SourcePolicy) -> Result<()> {
        resolve_source_values(self.extra.values_mut(), source_policy)
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct SandboxEnv {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub database: Option<String>,
    #[serde(default, flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PgDsnEnv {
    pub env_name: String,
    pub database: String,
    pub port: u16,
    pub password_env: String,
}
