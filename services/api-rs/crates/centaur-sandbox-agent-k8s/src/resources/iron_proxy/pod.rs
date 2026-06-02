use std::collections::BTreeMap;

use centaur_iron_proxy::SourceKind;
use centaur_sandbox_core::SandboxId;
use k8s_openapi::api::core::v1::{
    Capabilities, ConfigMapVolumeSource, Container, EnvFromSource, EnvVar, EnvVarSource, Pod,
    PodSpec, SeccompProfile, SecretEnvSource, SecretKeySelector, SecurityContext, Volume,
};

use super::config::ResolvedIronProxy;
use super::names::{iron_proxy_configmap_name, iron_proxy_labels, token_broker_url};
use crate::config::IronProxyPodConfig;
use crate::resources::common::{
    container_port, empty_dir_volume, env_var, health_probe, image_pull_secret_refs, object_meta,
    secret_volume, volume_mount,
};

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
        ports: Some(container_ports(resolved)),
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

fn container_ports(resolved: &ResolvedIronProxy) -> Vec<k8s_openapi::api::core::v1::ContainerPort> {
    let mut ports = vec![
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
        ports.push(container_port(format!("tcp-{port}"), port));
    }
    ports
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
