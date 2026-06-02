use std::collections::BTreeMap;

use centaur_sandbox_core::{SandboxError, SandboxResult};
use k8s_openapi::api::core::v1::PodSpec;
use serde::Serialize;

use crate::crd;

#[derive(Serialize)]
pub(super) struct AgentSandboxSpec {
    #[serde(rename = "podTemplate")]
    pub(super) pod_template: AgentPodTemplate,
    pub(super) replicas: Option<i32>,
    pub(super) service: Option<bool>,
    #[serde(rename = "shutdownPolicy")]
    pub(super) shutdown_policy: Option<crd::SandboxShutdownPolicy>,
}

#[derive(Serialize)]
pub(super) struct AgentPodTemplate {
    pub(super) metadata: AgentPodTemplateMetadata,
    pub(super) spec: PodSpec,
}

#[derive(Serialize)]
pub(super) struct AgentPodTemplateMetadata {
    pub(super) labels: Option<BTreeMap<String, String>>,
    pub(super) annotations: Option<BTreeMap<String, String>>,
}

pub(super) fn agent_sandbox_spec_from(spec: AgentSandboxSpec) -> SandboxResult<crd::SandboxSpec> {
    serde_json::to_value(spec)
        .and_then(serde_json::from_value)
        .map_err(|err| SandboxError::InvalidSpec(format!("invalid Agent Sandbox spec: {err}")))
}
