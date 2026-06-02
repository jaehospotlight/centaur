use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use centaur_iron_proxy::{ProxyFragment, SourceKind};
use centaur_sandbox_core::{
    MountKind, SandboxError, SandboxId, SandboxResult, SandboxSpec, SandboxStatus,
};
use k8s_openapi::api::core::v1::{
    Capabilities, ConfigMapVolumeSource, Container, ContainerPort, EmptyDirVolumeSource,
    EnvFromSource, EnvVar, EnvVarSource, HTTPGetAction, HostPathVolumeSource, LocalObjectReference,
    PersistentVolumeClaimVolumeSource, Pod, PodSpec, Probe, ResourceRequirements, SeccompProfile,
    SecretEnvSource, SecretKeySelector, SecretVolumeSource, SecurityContext, Service, ServicePort,
    ServiceSpec, Volume, VolumeMount,
};
use k8s_openapi::api::networking::v1::{
    NetworkPolicy, NetworkPolicyEgressRule, NetworkPolicyIngressRule, NetworkPolicyPeer,
    NetworkPolicyPort, NetworkPolicySpec,
};
use k8s_openapi::apimachinery::pkg::api::resource::Quantity;
use k8s_openapi::apimachinery::pkg::apis::meta::v1::{LabelSelector, ObjectMeta};
use k8s_openapi::apimachinery::pkg::util::intstr::IntOrString;
use serde::Serialize;
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::config::{AgentSandboxConfig, IronProxyPodConfig};
use crate::{
    MANAGED_BY_LABEL, MANAGED_BY_VALUE, MANAGED_LABEL, SANDBOX_ID_LABEL, TOKEN_BROKER_LABEL, crd,
};

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ResolvedIronProxy {
    pub(crate) config_yaml: String,
    pub(crate) placeholder_env: BTreeMap<String, String>,
    pub(crate) proxy_host: String,
    pub(crate) proxy_pod_name: String,
    pub(crate) proxy_port: u16,
    pub(crate) listen_ports: Vec<u16>,
    pub(crate) pg_dsn_env: BTreeMap<String, String>,
    pub(crate) pg_proxy_password_env: BTreeMap<String, String>,
}

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

pub(crate) fn proxied_pg_url(host: &str, port: u16, password: &str, database: &str) -> String {
    format!("postgresql://app_user:{password}@{host}:{port}/{database}")
}

pub(crate) fn proxy_password() -> String {
    Uuid::new_v4().simple().to_string()
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

pub(crate) fn iron_proxy_fragments_for_spec(
    iron_proxy: &IronProxyPodConfig,
    spec: &SandboxSpec,
) -> SandboxResult<Vec<ProxyFragment>> {
    let mut fragments =
        vec![centaur_iron_proxy::infra_fragment().map_err(|err| {
            SandboxError::InvalidSpec(format!("iron-proxy infra fragment: {err}"))
        })?];
    fragments.extend(iron_proxy.fragments.clone());
    for profile in &spec.credential_profiles {
        let harness = profile.as_str();
        let auth_mode = iron_proxy
            .harness_auth_modes
            .get(harness)
            .map(String::as_str)
            .unwrap_or("api_key");
        if let Some(fragment) = centaur_iron_proxy::harness_fragment(harness, auth_mode)
            .map_err(|err| SandboxError::InvalidSpec(format!("iron-proxy fragment: {err}")))?
        {
            fragments.push(fragment);
        }
    }
    Ok(fragments)
}

fn iron_proxy_container(
    iron_proxy: &IronProxyPodConfig,
    resolved: &ResolvedIronProxy,
) -> Container {
    let mut env = BTreeMap::<String, EnvVar>::new();
    if let Some(secret_name) = &iron_proxy.secret_env_name {
        insert_env_secret_ref(
            &mut env,
            "IRON_MANAGEMENT_API_KEY",
            secret_name,
            &iron_proxy.secret_env_prefix,
        );
    } else {
        insert_env_value(
            &mut env,
            "IRON_MANAGEMENT_API_KEY",
            "unused-local-sidecar-key",
        );
    }
    for (name, value) in &iron_proxy.extra_env {
        insert_env_value(&mut env, name, value);
    }
    if let Some(token_broker_name) = &iron_proxy.token_broker_name {
        insert_env_value(
            &mut env,
            "IRON_BROKER_URL",
            token_broker_url(token_broker_name),
        );
    }
    for (name, value) in &resolved.pg_proxy_password_env {
        insert_env_value(&mut env, name, value);
    }
    if let Some(secret_name) = &iron_proxy.secret_env_name {
        if matches!(
            iron_proxy.source_policy.kind,
            SourceKind::OnePasswordConnect
        ) {
            insert_env_secret_ref(
                &mut env,
                "OP_CONNECT_TOKEN",
                secret_name,
                &iron_proxy.secret_env_prefix,
            );
        }
        if iron_proxy.token_broker_name.is_some() {
            insert_env_secret_ref(
                &mut env,
                "IRON_BROKER_TOKEN",
                secret_name,
                &iron_proxy.secret_env_prefix,
            );
        }
    }
    let mut container_ports = vec![
        container_port("proxy", resolved.proxy_port),
        container_port("management", 9092),
        container_port("health", 9090),
    ];
    for port in resolved
        .listen_ports
        .iter()
        .copied()
        .filter(|port| ![resolved.proxy_port, 9092, 9090].contains(port))
    {
        container_ports.push(container_port(format!("tcp-{port}"), port));
    }

    Container {
        name: "iron-proxy".to_owned(),
        image: Some(iron_proxy.image.clone()),
        image_pull_policy: iron_proxy.image_pull_policy.clone(),
        env: Some(env.into_values().collect()),
        env_from: (!iron_proxy.env_from_secret_names.is_empty()).then(|| {
            iron_proxy
                .env_from_secret_names
                .iter()
                .map(|name| EnvFromSource {
                    secret_ref: Some(SecretEnvSource {
                        name: name.clone(),
                        ..Default::default()
                    }),
                    ..Default::default()
                })
                .collect()
        }),
        ports: Some(container_ports),
        readiness_probe: Some(health_probe(Some(5), Some(30))),
        liveness_probe: Some(health_probe(None, None)),
        security_context: Some(SecurityContext {
            allow_privilege_escalation: Some(false),
            capabilities: Some(Capabilities {
                drop: Some(vec!["ALL".to_owned()]),
                ..Default::default()
            }),
            seccomp_profile: Some(SeccompProfile {
                type_: "RuntimeDefault".to_owned(),
                ..Default::default()
            }),
            ..Default::default()
        }),
        volume_mounts: Some(vec![
            volume_mount("iron-proxy-config-rendered", "/etc/iron-proxy-rendered", true),
            volume_mount("iron-proxy-config", "/etc/iron-proxy", false),
            volume_mount("iron-proxy-certs", "/certs", false),
            volume_mount("iron-proxy-ca", "/etc/iron-proxy-ca", true),
        ]),
        command: Some(vec!["/bin/sh".to_owned(), "-ec".to_owned()]),
        args: Some(vec![
            "cp /etc/iron-proxy-rendered/proxy.yaml /etc/iron-proxy/proxy.yaml && exec /entrypoint.sh"
                .to_owned(),
        ]),
        ..Default::default()
    }
}

fn insert_env_value(env: &mut BTreeMap<String, EnvVar>, name: &str, value: impl AsRef<str>) {
    env.insert(name.to_owned(), env_var(name, value.as_ref()));
}

fn insert_env_secret_ref(
    env: &mut BTreeMap<String, EnvVar>,
    name: &str,
    secret_name: &str,
    secret_prefix: &str,
) {
    env.insert(
        name.to_owned(),
        EnvVar {
            name: name.to_owned(),
            value_from: Some(EnvVarSource {
                secret_key_ref: Some(SecretKeySelector {
                    name: secret_name.to_owned(),
                    key: format!("{secret_prefix}{name}"),
                    ..Default::default()
                }),
                ..Default::default()
            }),
            ..Default::default()
        },
    );
}

fn iron_proxy_volumes(id: &SandboxId, iron_proxy: &IronProxyPodConfig) -> Vec<Volume> {
    vec![
        Volume {
            name: "iron-proxy-config-rendered".to_owned(),
            config_map: Some(ConfigMapVolumeSource {
                name: iron_proxy_configmap_name(id),
                ..Default::default()
            }),
            ..Default::default()
        },
        empty_dir_volume("iron-proxy-config"),
        empty_dir_volume("iron-proxy-certs"),
        secret_volume("iron-proxy-ca", iron_proxy.ca_key_secret_name.clone()),
    ]
}

pub(crate) fn build_iron_proxy_pod(
    id: &SandboxId,
    pod_name: &str,
    iron_proxy: &IronProxyPodConfig,
    resolved: &ResolvedIronProxy,
) -> Pod {
    let labels = iron_proxy_labels(id);
    Pod {
        metadata: object_meta(pod_name, labels),
        spec: Some(PodSpec {
            automount_service_account_token: Some(false),
            restart_policy: Some("Never".to_owned()),
            containers: vec![iron_proxy_container(iron_proxy, resolved)],
            volumes: Some(iron_proxy_volumes(id, iron_proxy)),
            image_pull_secrets: image_pull_secret_refs(&iron_proxy.image_pull_secrets),
            ..Default::default()
        }),
        ..Default::default()
    }
}

pub(crate) fn build_iron_proxy_service(id: &SandboxId, resolved: &ResolvedIronProxy) -> Service {
    let mut ports = vec![service_port("proxy", resolved.proxy_port)];
    for port in resolved
        .listen_ports
        .iter()
        .copied()
        .filter(|port| *port != resolved.proxy_port)
    {
        ports.push(service_port(format!("tcp-{port}"), port));
    }
    Service {
        metadata: object_meta(iron_proxy_service_name(id), iron_proxy_labels(id)),
        spec: Some(ServiceSpec {
            selector: Some(iron_proxy_labels(id)),
            ports: Some(ports),
            ..Default::default()
        }),
        ..Default::default()
    }
}

pub(crate) fn build_iron_proxy_network_policies(
    id: &SandboxId,
    resolved: &ResolvedIronProxy,
    iron_proxy: &IronProxyPodConfig,
) -> Vec<NetworkPolicy> {
    let mut sandbox_to_proxy_ports = vec![network_port(resolved.proxy_port)];
    for port in resolved
        .listen_ports
        .iter()
        .copied()
        .filter(|port| *port != resolved.proxy_port)
    {
        sandbox_to_proxy_ports.push(network_port(port));
    }
    let sandbox_policy = NetworkPolicy {
        metadata: object_meta(
            iron_proxy_sandbox_egress_policy_name(id),
            sandbox_labels(id),
        ),
        spec: Some(NetworkPolicySpec {
            pod_selector: Some(label_selector(sandbox_labels(id))),
            policy_types: Some(vec!["Egress".to_owned()]),
            egress: Some(vec![
                egress_to(
                    vec![pod_peer(iron_proxy_labels(id))],
                    sandbox_to_proxy_ports.clone(),
                ),
                egress_to(
                    vec![pod_peer(iron_proxy.api_pod_labels.clone())],
                    vec![network_port(8000)],
                ),
                dns_egress_rule(),
            ]),
            ..Default::default()
        }),
    };
    let mut proxy_egress = vec![
        dns_egress_rule(),
        egress_to(
            vec![pod_peer(iron_proxy.api_pod_labels.clone())],
            vec![network_port(8000)],
        ),
        NetworkPolicyEgressRule {
            ports: Some(vec![network_port(443), network_port(5432)]),
            ..Default::default()
        },
    ];
    if iron_proxy.token_broker_name.is_some() {
        proxy_egress.push(egress_to(
            vec![pod_peer(token_broker_pod_labels())],
            vec![network_port(centaur_iron_proxy::DEFAULT_BROKER_LISTEN_PORT)],
        ));
    }
    if matches!(
        iron_proxy.source_policy.kind,
        SourceKind::OnePasswordConnect
    ) {
        proxy_egress.push(egress_to(
            vec![pod_peer(BTreeMap::from([(
                "app".to_owned(),
                iron_proxy.op_connect_app_name.clone(),
            )]))],
            vec![network_port(iron_proxy.op_connect_port)],
        ));
    }
    let proxy_policy = NetworkPolicy {
        metadata: object_meta(iron_proxy_policy_name(id), iron_proxy_labels(id)),
        spec: Some(NetworkPolicySpec {
            pod_selector: Some(label_selector(iron_proxy_labels(id))),
            policy_types: Some(vec!["Ingress".to_owned(), "Egress".to_owned()]),
            ingress: Some(vec![NetworkPolicyIngressRule {
                from: Some(vec![pod_peer(sandbox_labels(id))]),
                ports: Some(sandbox_to_proxy_ports),
            }]),
            egress: Some(proxy_egress),
        }),
    };
    vec![sandbox_policy, proxy_policy]
}

fn dns_egress_rule() -> NetworkPolicyEgressRule {
    egress_to(
        vec![NetworkPolicyPeer {
            namespace_selector: Some(label_selector(BTreeMap::from([(
                "kubernetes.io/metadata.name".to_owned(),
                "kube-system".to_owned(),
            )]))),
            ..Default::default()
        }],
        vec![udp_port(53), network_port(53)],
    )
}

pub(crate) fn object_meta(name: impl Into<String>, labels: BTreeMap<String, String>) -> ObjectMeta {
    ObjectMeta {
        name: Some(name.into()),
        labels: Some(labels),
        ..Default::default()
    }
}

fn env_var(name: &str, value: &str) -> EnvVar {
    EnvVar {
        name: name.to_owned(),
        value: Some(value.to_owned()),
        ..Default::default()
    }
}

fn container_port(name: impl Into<String>, port: u16) -> ContainerPort {
    ContainerPort {
        name: Some(name.into()),
        container_port: i32::from(port),
        ..Default::default()
    }
}

fn service_port(name: impl Into<String>, port: u16) -> ServicePort {
    let port = i32::from(port);
    ServicePort {
        name: Some(name.into()),
        port,
        target_port: Some(IntOrString::Int(port)),
        protocol: Some("TCP".to_owned()),
        ..Default::default()
    }
}

fn network_port(port: u16) -> NetworkPolicyPort {
    policy_port("TCP", port)
}

fn udp_port(port: u16) -> NetworkPolicyPort {
    policy_port("UDP", port)
}

fn policy_port(protocol: &str, port: u16) -> NetworkPolicyPort {
    NetworkPolicyPort {
        port: Some(IntOrString::Int(i32::from(port))),
        protocol: Some(protocol.to_owned()),
        ..Default::default()
    }
}

fn health_probe(period_seconds: Option<i32>, failure_threshold: Option<i32>) -> Probe {
    Probe {
        http_get: Some(HTTPGetAction {
            path: Some("/healthz".to_owned()),
            port: IntOrString::Int(9090),
            ..Default::default()
        }),
        period_seconds,
        failure_threshold,
        ..Default::default()
    }
}

fn volume_mount(name: &str, mount_path: &str, read_only: bool) -> VolumeMount {
    VolumeMount {
        name: name.to_owned(),
        mount_path: mount_path.to_owned(),
        read_only: read_only.then_some(true),
        ..Default::default()
    }
}

fn empty_dir_volume(name: &str) -> Volume {
    Volume {
        name: name.to_owned(),
        empty_dir: Some(EmptyDirVolumeSource::default()),
        ..Default::default()
    }
}

fn secret_volume(name: &str, secret_name: impl Into<String>) -> Volume {
    Volume {
        name: name.to_owned(),
        secret: Some(SecretVolumeSource {
            secret_name: Some(secret_name.into()),
            ..Default::default()
        }),
        ..Default::default()
    }
}

fn label_selector(match_labels: BTreeMap<String, String>) -> LabelSelector {
    LabelSelector {
        match_labels: Some(match_labels),
        ..Default::default()
    }
}

fn pod_peer(match_labels: BTreeMap<String, String>) -> NetworkPolicyPeer {
    NetworkPolicyPeer {
        pod_selector: Some(label_selector(match_labels)),
        ..Default::default()
    }
}

fn egress_to(to: Vec<NetworkPolicyPeer>, ports: Vec<NetworkPolicyPort>) -> NetworkPolicyEgressRule {
    NetworkPolicyEgressRule {
        to: Some(to),
        ports: Some(ports),
    }
}

fn resources(spec: &SandboxSpec) -> Option<ResourceRequirements> {
    let resources = spec.resources.as_ref()?;
    let mut limits = BTreeMap::new();
    if let Some(cpu_millis) = resources.cpu_millis {
        limits.insert("cpu".to_owned(), Quantity(format!("{cpu_millis}m")));
    }
    if let Some(memory_bytes) = resources.memory_bytes {
        limits.insert("memory".to_owned(), Quantity(memory_bytes.to_string()));
    }
    (!limits.is_empty()).then(|| ResourceRequirements {
        limits: Some(limits),
        ..Default::default()
    })
}

pub(crate) fn iron_proxy_configmap_name(id: &SandboxId) -> String {
    format!("{}-iron-proxy", id.as_str())
}

pub(crate) fn iron_proxy_pod_name(id: &SandboxId) -> String {
    format!("{}-proxy", id.as_str())
}

pub(crate) fn new_iron_proxy_pod_name(id: &SandboxId) -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let sequence = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    format!("{}-proxy-{millis}-{sequence}", id.as_str())
}

pub(crate) fn iron_proxy_service_name(id: &SandboxId) -> String {
    format!("{}-proxy", id.as_str())
}

pub(crate) fn iron_proxy_sandbox_egress_policy_name(id: &SandboxId) -> String {
    format!("{}-sandbox-egress", id.as_str())
}

pub(crate) fn iron_proxy_policy_name(id: &SandboxId) -> String {
    format!("{}-proxy-net", id.as_str())
}

fn sandbox_labels(id: &SandboxId) -> BTreeMap<String, String> {
    BTreeMap::from([
        (MANAGED_BY_LABEL.to_owned(), MANAGED_BY_VALUE.to_owned()),
        (SANDBOX_ID_LABEL.to_owned(), id.as_str().to_owned()),
        (MANAGED_LABEL.to_owned(), "true".to_owned()),
    ])
}

pub(crate) fn iron_proxy_labels(id: &SandboxId) -> BTreeMap<String, String> {
    BTreeMap::from([
        (MANAGED_BY_LABEL.to_owned(), MANAGED_BY_VALUE.to_owned()),
        (SANDBOX_ID_LABEL.to_owned(), id.as_str().to_owned()),
        ("centaur.ai/iron-proxy".to_owned(), "true".to_owned()),
    ])
}

pub(crate) fn iron_token_broker_configmap_name(
    iron_proxy: &IronProxyPodConfig,
) -> SandboxResult<String> {
    if let Some(name) = iron_proxy.token_broker_configmap_name.as_deref() {
        return Ok(name.to_owned());
    }
    let Some(name) = iron_proxy.token_broker_name.as_deref() else {
        return Err(SandboxError::InvalidSpec(
            "iron-token-broker configmap requires token_broker_name".to_owned(),
        ));
    };
    Ok(format!("{name}-config"))
}

fn token_broker_url(name: &str) -> String {
    format!(
        "http://{name}:{}",
        centaur_iron_proxy::DEFAULT_BROKER_LISTEN_PORT
    )
}

pub(crate) fn token_broker_labels() -> BTreeMap<String, String> {
    let mut labels = token_broker_pod_labels();
    labels.insert(TOKEN_BROKER_LABEL.to_owned(), "true".to_owned());
    labels
}

pub(crate) fn token_broker_pod_labels() -> BTreeMap<String, String> {
    BTreeMap::from([(
        "app.kubernetes.io/component".to_owned(),
        "token-broker".to_owned(),
    )])
}

pub(crate) fn short_sha256(value: &str) -> String {
    let digest = Sha256::digest(value.as_bytes());
    digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn image_pull_secret_refs(names: &[String]) -> Option<Vec<LocalObjectReference>> {
    (!names.is_empty()).then(|| {
        names
            .iter()
            .map(|name| LocalObjectReference { name: name.clone() })
            .collect::<Vec<_>>()
    })
}

pub(crate) fn next_sandbox_name() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let sequence = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    format!("asbx-{millis}-{sequence}")
}
