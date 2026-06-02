use std::collections::BTreeMap;

use centaur_sandbox_core::{
    MountKind, SandboxError, SandboxId, SandboxResult, SandboxSpec, SandboxStatus,
};
use k8s_openapi::api::core::v1::{
    Container, EnvVar, HostPathVolumeSource, PersistentVolumeClaimVolumeSource, Pod, PodSpec,
    Volume, VolumeMount,
};
use serde::Serialize;

use super::common::{
    empty_dir_volume, env_var, image_pull_secret_refs, resources, secret_volume, volume_mount,
};
use super::iron_proxy::ResolvedIronProxy;
use crate::config::AgentSandboxConfig;
use crate::{MANAGED_BY_LABEL, MANAGED_BY_VALUE, MANAGED_LABEL, SANDBOX_ID_LABEL, crd};

pub(crate) fn sandbox_status_from_pod(replicas: i32, pod: Option<&Pod>) -> SandboxStatus {
    if replicas == 0 {
        return SandboxStatus::Suspended;
    }
    // The backing Pod Ready condition is the attach boundary; phase alone can be Running while
    // the sandbox is still not ready for I/O.
    let Some(pod) = pod else {
        return SandboxStatus::Created;
    };
    if pod.metadata.deletion_timestamp.is_some() {
        return SandboxStatus::Created;
    }

    let phase = pod
        .status
        .as_ref()
        .and_then(|status| status.phase.as_deref())
        .unwrap_or("unknown")
        .to_ascii_lowercase();
    match phase.as_str() {
        "running" if pod_ready(pod) => SandboxStatus::Running,
        "running" | "pending" => SandboxStatus::Created,
        "succeeded" | "failed" => SandboxStatus::Stopped,
        "unknown" => SandboxStatus::Unknown("unknown".to_owned()),
        other => SandboxStatus::Unknown(other.to_owned()),
    }
}

fn pod_ready(pod: &Pod) -> bool {
    pod.status
        .as_ref()
        .and_then(|status| status.conditions.as_ref())
        .is_some_and(|conditions| {
            conditions
                .iter()
                .any(|condition| condition.type_ == "Ready" && condition.status == "True")
        })
}

pub(crate) fn build_agent_sandbox(
    id: &SandboxId,
    spec: &SandboxSpec,
    config: &AgentSandboxConfig,
    resolved_iron_proxy: Option<&ResolvedIronProxy>,
) -> SandboxResult<crd::Sandbox> {
    let mut labels = config.labels.clone();
    labels.insert(MANAGED_LABEL.to_owned(), "true".to_owned());
    labels.insert(MANAGED_BY_LABEL.to_owned(), MANAGED_BY_VALUE.to_owned());
    labels.insert(SANDBOX_ID_LABEL.to_owned(), id.as_str().to_owned());

    let mut pod_labels = labels.clone();
    pod_labels.insert(
        "app.kubernetes.io/name".to_owned(),
        "centaur-sandbox".to_owned(),
    );

    let (mut volumes, mut volume_mounts) = mounts(spec);
    if let Some(iron_proxy) = &config.iron_proxy {
        volume_mounts.push(volume_mount("iron-proxy-ca-cert", "/firewall-certs", true));
        volumes.push(secret_volume(
            "iron-proxy-ca-cert",
            iron_proxy.ca_cert_secret_name.clone(),
        ));
    }

    let container = Container {
        name: config.container_name.clone(),
        image: Some(spec.image.clone()),
        image_pull_policy: config.image_pull_policy.clone(),
        command: spec.command.clone(),
        args: (!spec.args.is_empty()).then(|| spec.args.clone()),
        env: env_vars(spec, resolved_iron_proxy),
        working_dir: spec.working_dir.clone(),
        resources: resources(spec),
        stdin: Some(true),
        stdin_once: Some(false),
        tty: Some(false),
        volume_mounts: (!volume_mounts.is_empty()).then_some(volume_mounts),
        ..Default::default()
    };

    let crd_spec = agent_sandbox_spec_from(AgentSandboxSpec {
        replicas: Some(1),
        service: Some(false),
        shutdown_policy: Some(crd::SandboxShutdownPolicy::Retain),
        pod_template: AgentPodTemplate {
            metadata: AgentPodTemplateMetadata {
                labels: Some(pod_labels),
                annotations: Some(config.annotations.clone()),
            },
            spec: PodSpec {
                containers: vec![container],
                restart_policy: Some("Never".to_owned()),
                automount_service_account_token: Some(false),
                image_pull_secrets: image_pull_secret_refs(&config.image_pull_secrets),
                runtime_class_name: config.runtime_class_name.clone(),
                service_account_name: config.service_account_name.clone(),
                volumes: (!volumes.is_empty()).then_some(volumes),
                ..Default::default()
            },
        },
    })?;
    let mut sandbox = crd::Sandbox::new(id.as_str(), crd_spec);
    sandbox.metadata.labels = Some(labels);
    sandbox.metadata.annotations = Some(config.annotations.clone());
    Ok(sandbox)
}

#[derive(Serialize)]
struct AgentSandboxSpec {
    #[serde(rename = "podTemplate")]
    pod_template: AgentPodTemplate,
    replicas: Option<i32>,
    service: Option<bool>,
    #[serde(rename = "shutdownPolicy")]
    shutdown_policy: Option<crd::SandboxShutdownPolicy>,
}

#[derive(Serialize)]
struct AgentPodTemplate {
    metadata: AgentPodTemplateMetadata,
    spec: PodSpec,
}

#[derive(Serialize)]
struct AgentPodTemplateMetadata {
    labels: Option<BTreeMap<String, String>>,
    annotations: Option<BTreeMap<String, String>>,
}

fn agent_sandbox_spec_from(spec: AgentSandboxSpec) -> SandboxResult<crd::SandboxSpec> {
    serde_json::to_value(spec)
        .and_then(serde_json::from_value)
        .map_err(|err| SandboxError::InvalidSpec(format!("invalid Agent Sandbox spec: {err}")))
}

fn mounts(spec: &SandboxSpec) -> (Vec<Volume>, Vec<VolumeMount>) {
    let mut volumes = Vec::with_capacity(spec.mounts.len());
    let mut mounts = Vec::with_capacity(spec.mounts.len());
    for (index, mount) in spec.mounts.iter().enumerate() {
        let name = format!("mount-{index}");
        mounts.push(VolumeMount {
            name: name.clone(),
            mount_path: mount.target_path.clone(),
            read_only: Some(mount.read_only),
            ..Default::default()
        });
        volumes.push(match &mount.kind {
            MountKind::EmptyDir => empty_dir_volume(&name),
            MountKind::NamedVolume(claim_name) => Volume {
                name,
                persistent_volume_claim: Some(PersistentVolumeClaimVolumeSource {
                    claim_name: claim_name.clone(),
                    read_only: Some(mount.read_only),
                }),
                ..Default::default()
            },
            MountKind::Bind { source_path } => Volume {
                name,
                host_path: Some(HostPathVolumeSource {
                    path: source_path.clone(),
                    ..Default::default()
                }),
                ..Default::default()
            },
        });
    }
    (volumes, mounts)
}

fn env_vars(
    spec: &SandboxSpec,
    resolved_iron_proxy: Option<&ResolvedIronProxy>,
) -> Option<Vec<EnvVar>> {
    let mut env = BTreeMap::<String, String>::new();
    for item in &spec.env {
        env.insert(item.name.clone(), item.value.clone());
    }
    if let Some(resolved_iron_proxy) = resolved_iron_proxy {
        for (name, value) in &resolved_iron_proxy.placeholder_env {
            env.entry(name.clone()).or_insert_with(|| value.clone());
        }
        for (name, value) in &resolved_iron_proxy.pg_dsn_env {
            env.entry(name.clone()).or_insert_with(|| value.clone());
        }
        let api_host = env
            .get("CENTAUR_API_URL")
            .and_then(|value| host_from_url(value));
        let no_proxy_extra = ["NO_PROXY", "no_proxy"]
            .into_iter()
            .filter_map(|name| env.get(name).map(String::as_str))
            .collect::<Vec<_>>();
        for (name, value) in proxy_env(
            &resolved_iron_proxy.proxy_host,
            resolved_iron_proxy.proxy_port,
            api_host.as_deref(),
            &no_proxy_extra,
        ) {
            env.insert(name, value);
        }
    }
    (!env.is_empty()).then(|| {
        env.into_iter()
            .map(|(name, value)| env_var(&name, &value))
            .collect()
    })
}

fn proxy_env(
    proxy_host: &str,
    proxy_port: u16,
    api_host: Option<&str>,
    no_proxy_extra: &[&str],
) -> BTreeMap<String, String> {
    let proxy_url = format!("http://{proxy_host}:{proxy_port}");
    let no_proxy = no_proxy_value(proxy_host, api_host, no_proxy_extra);
    BTreeMap::from([
        ("FIREWALL_HOST".to_owned(), proxy_host.to_owned()),
        ("FIREWALL_PROXY_PORT".to_owned(), proxy_port.to_string()),
        ("HTTP_PROXY".to_owned(), proxy_url.clone()),
        ("HTTPS_PROXY".to_owned(), proxy_url.clone()),
        ("http_proxy".to_owned(), proxy_url.clone()),
        ("https_proxy".to_owned(), proxy_url),
        ("NO_PROXY".to_owned(), no_proxy.clone()),
        ("no_proxy".to_owned(), no_proxy),
        (
            "NODE_EXTRA_CA_CERTS".to_owned(),
            "/firewall-certs/ca-cert.pem".to_owned(),
        ),
        (
            "REQUESTS_CA_BUNDLE".to_owned(),
            "/firewall-certs/ca-cert.pem".to_owned(),
        ),
        (
            "CURL_CA_BUNDLE".to_owned(),
            "/firewall-certs/ca-cert.pem".to_owned(),
        ),
        (
            "SSL_CERT_FILE".to_owned(),
            "/firewall-certs/ca-cert.pem".to_owned(),
        ),
        (
            "GIT_SSL_CAINFO".to_owned(),
            "/firewall-certs/ca-cert.pem".to_owned(),
        ),
    ])
}

fn no_proxy_value(proxy_host: &str, api_host: Option<&str>, extra_values: &[&str]) -> String {
    let mut hosts = vec![
        "localhost".to_owned(),
        "127.0.0.1".to_owned(),
        "::1".to_owned(),
        proxy_host.to_owned(),
        "api".to_owned(),
        "victoriametrics".to_owned(),
        "victorialogs".to_owned(),
    ];
    if let Some(api_host) = api_host.filter(|value| !value.is_empty()) {
        hosts.push(api_host.to_owned());
    }
    for value in extra_values {
        hosts.extend(
            value
                .split(',')
                .map(str::trim)
                .filter(|host| !host.is_empty())
                .map(ToOwned::to_owned),
        );
    }
    let mut deduped = Vec::new();
    for host in hosts {
        if !deduped.contains(&host) {
            deduped.push(host);
        }
    }
    deduped.join(",")
}

fn host_from_url(value: &str) -> Option<String> {
    let value = value.trim();
    let without_scheme = value
        .split_once("://")
        .map(|(_, rest)| rest)
        .unwrap_or(value);
    let authority = without_scheme.split('/').next()?.trim();
    let host_port = authority
        .rsplit_once('@')
        .map(|(_, host_port)| host_port)
        .unwrap_or(authority);
    let host = host_port
        .split_once(':')
        .map_or(host_port, |(host, _)| host);
    (!host.is_empty()).then(|| host.to_owned())
}
