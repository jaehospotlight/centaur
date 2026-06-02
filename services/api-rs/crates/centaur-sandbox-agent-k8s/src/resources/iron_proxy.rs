use std::collections::BTreeMap;

use centaur_iron_proxy::{ProxyFragment, SourceKind};
use centaur_sandbox_core::{SandboxError, SandboxId, SandboxResult, SandboxSpec};
use k8s_openapi::api::core::v1::{
    Capabilities, ConfigMapVolumeSource, Container, EnvFromSource, EnvVar, EnvVarSource, Pod,
    PodSpec, SeccompProfile, SecretEnvSource, SecretKeySelector, SecurityContext, Service,
    ServiceSpec, Volume,
};
use k8s_openapi::api::networking::v1::{
    NetworkPolicy, NetworkPolicyEgressRule, NetworkPolicyIngressRule, NetworkPolicyPeer,
    NetworkPolicySpec,
};
use uuid::Uuid;

use super::common::{
    container_port, egress_to, empty_dir_volume, env_var, health_probe, image_pull_secret_refs,
    label_selector, network_port, object_meta, pod_peer, secret_volume, service_port, udp_port,
    unique_suffix, volume_mount,
};
use crate::config::IronProxyPodConfig;
use crate::{
    MANAGED_BY_LABEL, MANAGED_BY_VALUE, MANAGED_LABEL, SANDBOX_ID_LABEL, TOKEN_BROKER_LABEL,
};

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

pub(crate) fn proxied_pg_url(host: &str, port: u16, password: &str, database: &str) -> String {
    format!("postgresql://app_user:{password}@{host}:{port}/{database}")
}

pub(crate) fn proxy_password() -> String {
    Uuid::new_v4().simple().to_string()
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

pub(crate) fn iron_proxy_configmap_name(id: &SandboxId) -> String {
    format!("{}-iron-proxy", id.as_str())
}

pub(crate) fn iron_proxy_pod_name(id: &SandboxId) -> String {
    format!("{}-proxy", id.as_str())
}

pub(crate) fn new_iron_proxy_pod_name(id: &SandboxId) -> String {
    format!("{}-proxy-{}", id.as_str(), unique_suffix())
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
