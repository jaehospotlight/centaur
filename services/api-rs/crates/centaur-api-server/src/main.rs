use std::{collections::BTreeMap, env, net::SocketAddr, path::PathBuf, sync::Arc, time::Duration};

use centaur_api_server::{SandboxRuntime, build_router_with_runtime};
use centaur_iron_proxy::{SourceKind, SourcePolicy, discover_fragment_files, load_fragment_files};
use centaur_sandbox_agent_k8s::{
    AgentSandboxBackend, AgentSandboxConfig, IronProxyPodConfig, StateVolumeConfig,
};
use centaur_sandbox_core::{Mount, MountKind, SandboxSpec};
use centaur_sandbox_local::LocalSandboxBackend;
use centaur_session_core::ThreadKey;
use centaur_session_runtime::SandboxWorkloadMode;
use centaur_session_sqlx::PgSessionStore;
use clap::{Parser, ValueEnum};
use thiserror::Error;
use tokio::net::TcpListener;
use tracing::info;
use tracing_subscriber::{EnvFilter, fmt as tracing_fmt};

const SANDBOX_REPOS_MOUNT_PATH: &str = "/home/agent/github";

#[tokio::main]
async fn main() -> Result<(), ServerError> {
    init_tracing();

    let args = Args::parse();

    let store = PgSessionStore::connect(&args.database_url).await?;
    if args.run_migrations {
        store.run_migrations().await?;
    }
    let sandbox_runtime = sandbox_runtime_from_args(&args).await?;

    let listener = TcpListener::bind(args.bind_addr).await?;
    info!(bind_addr = %args.bind_addr, "starting centaur api-rs server");

    axum::serve(listener, build_router_with_runtime(store, sandbox_runtime))
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_fmt().with_env_filter(filter).json().init();
}

async fn shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

async fn sandbox_runtime_from_args(args: &Args) -> Result<SandboxRuntime, ServerError> {
    match args.session_sandbox_backend {
        SandboxBackendKind::Local => Ok(SandboxRuntime::backend_with_workload(
            Arc::new(LocalSandboxBackend::new()),
            local_workload_mode(args)?,
        )),
        SandboxBackendKind::AgentK8s => {
            let mut config = agent_sandbox_config_from_args(args)?;
            config.ready_timeout = Duration::from_secs(args.session_sandbox_ready_timeout_secs);

            let client = if let Some(context) = args.session_sandbox_k8s_context.as_deref() {
                let kube_config = kube::Config::from_kubeconfig(&kube::config::KubeConfigOptions {
                    context: Some(context.to_owned()),
                    ..kube::config::KubeConfigOptions::default()
                })
                .await?;
                kube::Client::try_from(kube_config)?
            } else {
                kube::Client::try_default().await?
            };
            let backend = Arc::new(AgentSandboxBackend::new(client, config));

            Ok(container_sandbox_runtime(backend, args))
        }
    }
}

fn local_workload_mode(args: &Args) -> Result<SandboxWorkloadMode, ServerError> {
    match args.session_sandbox_workload {
        SandboxWorkloadKind::Mock => Ok(SandboxWorkloadMode::mock_app_server(
            args.session_sandbox_image
                .clone()
                .unwrap_or_else(|| "local-mock-app-server".to_owned()),
        )),
        SandboxWorkloadKind::CodexAppServer => Err(ServerError::UnsupportedConfig(
            "codex-app-server workload requires --session-sandbox-backend agent-k8s".to_owned(),
        )),
    }
}

fn container_sandbox_runtime(backend: Arc<AgentSandboxBackend>, args: &Args) -> SandboxRuntime {
    if args.session_sandbox_workload == SandboxWorkloadKind::CodexAppServer {
        if let Some(repos_path) = sandbox_repos_path_from_args(args) {
            let image = args
                .session_sandbox_image
                .clone()
                .unwrap_or_else(|| default_sandbox_image(args.session_sandbox_workload).to_owned());
            let env_template = codex_app_server_env_template(args);
            return SandboxRuntime::backend_with_spec_factory(
                backend,
                move |thread_key, _execution_id| {
                    codex_app_server_spec(
                        &image,
                        thread_key,
                        &env_template,
                        Some(repos_path.as_str()),
                    )
                },
            );
        }
    }

    SandboxRuntime::backend_with_workload(backend, container_workload_mode(args))
}

fn container_workload_mode(args: &Args) -> SandboxWorkloadMode {
    let image = args
        .session_sandbox_image
        .clone()
        .unwrap_or_else(|| default_sandbox_image(args.session_sandbox_workload).to_owned());
    match args.session_sandbox_workload {
        SandboxWorkloadKind::Mock => SandboxWorkloadMode::mock_app_server(image),
        SandboxWorkloadKind::CodexAppServer => {
            SandboxWorkloadMode::codex_app_server(image, codex_app_server_env_template(args))
        }
    }
}

#[derive(Debug, Parser)]
#[command(about = "Run the Centaur API Rust session control plane")]
struct Args {
    #[arg(long, env = "DATABASE_URL")]
    database_url: String,
    #[arg(long, env = "BIND_ADDR", default_value = "127.0.0.1:8080")]
    bind_addr: SocketAddr,
    #[arg(long, env = "RUN_MIGRATIONS", default_value_t = false)]
    run_migrations: bool,
    #[arg(
        long,
        env = "SESSION_SANDBOX_BACKEND",
        value_enum,
        default_value = "local"
    )]
    session_sandbox_backend: SandboxBackendKind,
    #[arg(
        long,
        env = "SESSION_SANDBOX_WORKLOAD",
        value_enum,
        default_value = "mock"
    )]
    session_sandbox_workload: SandboxWorkloadKind,
    #[arg(
        long,
        env = "SESSION_SANDBOX_K8S_NAMESPACE",
        default_value = "centaur-sandbox-e2e"
    )]
    session_sandbox_k8s_namespace: String,
    #[arg(long, env = "SESSION_SANDBOX_IMAGE")]
    session_sandbox_image: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IMAGE_PULL_POLICY")]
    session_sandbox_image_pull_policy: Option<String>,
    #[arg(long, env = "KUBERNETES_AGENT_IMAGE_PULL_POLICY", hide = true)]
    kubernetes_agent_image_pull_policy: Option<String>,
    #[arg(
        long,
        env = "SESSION_SANDBOX_IMAGE_PULL_SECRETS",
        value_delimiter = ','
    )]
    session_sandbox_image_pull_secrets: Vec<String>,
    #[arg(
        long,
        env = "KUBERNETES_SANDBOX_IMAGE_PULL_SECRETS",
        value_delimiter = ',',
        hide = true
    )]
    kubernetes_sandbox_image_pull_secrets: Vec<String>,
    #[arg(long, env = "SESSION_SANDBOX_READY_TIMEOUT_SECS", default_value_t = 90)]
    session_sandbox_ready_timeout_secs: u64,
    #[arg(long, env = "SESSION_SANDBOX_K8S_CONTEXT")]
    session_sandbox_k8s_context: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_RUNTIME_CLASS_NAME")]
    session_sandbox_runtime_class_name: Option<String>,
    #[arg(long, env = "KUBERNETES_SANDBOX_RUNTIME_CLASS_NAME", hide = true)]
    kubernetes_sandbox_runtime_class_name: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_SERVICE_ACCOUNT_NAME")]
    session_sandbox_service_account_name: Option<String>,
    #[arg(long, env = "KUBERNETES_SANDBOX_SERVICE_ACCOUNT_NAME", hide = true)]
    kubernetes_sandbox_service_account_name: Option<String>,
    #[arg(
        long,
        env = "SESSION_SANDBOX_STATE_VOLUME_ENABLED",
        value_parser = parse_bool_arg
    )]
    session_sandbox_state_volume_enabled: Option<bool>,
    #[arg(
        long,
        env = "KUBERNETES_SANDBOX_STATE_VOLUME_ENABLED",
        value_parser = parse_bool_arg,
        hide = true
    )]
    kubernetes_sandbox_state_volume_enabled: Option<bool>,
    #[arg(long, env = "SESSION_SANDBOX_STATE_MOUNT_PATH")]
    session_sandbox_state_mount_path: Option<String>,
    #[arg(long, env = "KUBERNETES_SANDBOX_STATE_MOUNT_PATH", hide = true)]
    kubernetes_sandbox_state_mount_path: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_STATE_VOLUME_SIZE")]
    session_sandbox_state_volume_size: Option<String>,
    #[arg(long, env = "KUBERNETES_SANDBOX_STATE_VOLUME_SIZE", hide = true)]
    kubernetes_sandbox_state_volume_size: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_STATE_VOLUME_STORAGE_CLASS")]
    session_sandbox_state_volume_storage_class: Option<String>,
    #[arg(
        long,
        env = "KUBERNETES_SANDBOX_STATE_VOLUME_STORAGE_CLASS",
        hide = true
    )]
    kubernetes_sandbox_state_volume_storage_class: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_REPOS_PATH")]
    session_sandbox_repos_path: Option<String>,
    #[arg(long, env = "REPOS_PATH", hide = true)]
    repos_path: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_CENTAUR_API_URL")]
    session_sandbox_centaur_api_url: Option<String>,
    #[arg(long, env = "CENTAUR_API_URL")]
    centaur_api_url: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_CENTAUR_API_KEY")]
    session_sandbox_centaur_api_key: Option<String>,
    #[arg(long, env = "CENTAUR_API_KEY")]
    centaur_api_key: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_PASSTHROUGH_ENV", value_delimiter = ',')]
    session_sandbox_passthrough_env: Vec<String>,
    #[arg(long, env = "CODEX_AUTH_MODE")]
    codex_auth_mode: Option<String>,
    #[arg(long, env = "CLAUDE_CODE_AUTH_MODE")]
    claude_code_auth_mode: Option<String>,
    #[arg(
        long,
        env = "SESSION_SANDBOX_IRON_PROXY_ENABLED",
        value_parser = parse_bool_arg
    )]
    session_sandbox_iron_proxy_enabled: Option<bool>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_PROXY_IMAGE")]
    session_sandbox_iron_proxy_image: Option<String>,
    #[arg(long, env = "KUBERNETES_IRON_PROXY_IMAGE", hide = true)]
    kubernetes_iron_proxy_image: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_PROXY_IMAGE_PULL_POLICY")]
    session_sandbox_iron_proxy_image_pull_policy: Option<String>,
    #[arg(long, env = "KUBERNETES_IRON_PROXY_IMAGE_PULL_POLICY", hide = true)]
    kubernetes_iron_proxy_image_pull_policy: Option<String>,
    #[arg(
        long,
        env = "SESSION_SANDBOX_IRON_PROXY_FRAGMENT_PATHS",
        value_delimiter = ','
    )]
    session_sandbox_iron_proxy_fragment_paths: Vec<PathBuf>,
    #[arg(
        long,
        env = "SESSION_SANDBOX_IRON_PROXY_FRAGMENT_DIRS",
        value_delimiter = ','
    )]
    session_sandbox_iron_proxy_fragment_dirs: Vec<PathBuf>,
    #[arg(long, env = "TOOL_DIRS", value_delimiter = ':', hide = true)]
    tool_dirs: Vec<PathBuf>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_PROXY_CA_CERT_SECRET_NAME")]
    session_sandbox_iron_proxy_ca_cert_secret_name: Option<String>,
    #[arg(long, env = "KUBERNETES_FIREWALL_CA_SECRET_NAME", hide = true)]
    kubernetes_firewall_ca_secret_name: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_PROXY_CA_KEY_SECRET_NAME")]
    session_sandbox_iron_proxy_ca_key_secret_name: Option<String>,
    #[arg(long, env = "KUBERNETES_FIREWALL_CA_KEY_SECRET_NAME", hide = true)]
    kubernetes_firewall_ca_key_secret_name: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_PROXY_ENV_SECRET")]
    session_sandbox_iron_proxy_env_secret: Option<String>,
    #[arg(long, env = "KUBERNETES_SECRET_ENV_NAME", hide = true)]
    kubernetes_secret_env_name: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_PROXY_ENV_SECRET_PREFIX")]
    session_sandbox_iron_proxy_env_secret_prefix: Option<String>,
    #[arg(long, env = "KUBERNETES_SECRET_ENV_PREFIX", hide = true)]
    kubernetes_secret_env_prefix: Option<String>,
    #[arg(long, env = "KUBERNETES_BOOTSTRAP_SECRET_NAME", hide = true)]
    kubernetes_bootstrap_secret_name: Option<String>,
    #[arg(long, env = "FIREWALL_MANAGER_SECRET_SOURCE", value_enum)]
    firewall_manager_secret_source: Option<IronProxySecretSourceArg>,
    #[arg(
        long,
        env = "KUBERNETES_FIREWALL_MANAGER_SECRET_SOURCE",
        value_enum,
        hide = true
    )]
    kubernetes_firewall_manager_secret_source: Option<IronProxySecretSourceArg>,
    #[arg(long, env = "OP_VAULT")]
    op_vault: Option<String>,
    #[arg(long, env = "FIREWALL_MANAGER_SECRET_TTL")]
    firewall_manager_secret_ttl: Option<String>,
    #[arg(long, env = "KUBERNETES_FIREWALL_MANAGER_SECRET_TTL", hide = true)]
    kubernetes_firewall_manager_secret_ttl: Option<String>,
    #[arg(long, env = "FIREWALL_MANAGER_TOKEN_BROKER_TTL")]
    firewall_manager_token_broker_ttl: Option<String>,
    #[arg(
        long,
        env = "KUBERNETES_FIREWALL_MANAGER_TOKEN_BROKER_TTL",
        hide = true
    )]
    kubernetes_firewall_manager_token_broker_ttl: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_OP_CONNECT_HOST")]
    session_sandbox_op_connect_host: Option<String>,
    #[arg(long, env = "KUBERNETES_OP_CONNECT_HOST", hide = true)]
    kubernetes_op_connect_host: Option<String>,
    #[arg(long, env = "KUBERNETES_OP_CONNECT_APP_NAME", hide = true)]
    kubernetes_op_connect_app_name: Option<String>,
    #[arg(long, env = "KUBERNETES_OP_CONNECT_PORT", hide = true)]
    kubernetes_op_connect_port: Option<u16>,
    #[arg(
        long,
        env = "KUBERNETES_API_POD_LABEL_SELECTOR",
        value_parser = parse_label_selector_arg,
        hide = true
    )]
    kubernetes_api_pod_label_selector: Option<BTreeMap<String, String>>,
    #[arg(
        long,
        env = "SESSION_SANDBOX_IRON_BROKER_POD_LABEL_SELECTOR",
        value_parser = parse_label_selector_arg
    )]
    session_sandbox_iron_broker_pod_label_selector: Option<BTreeMap<String, String>>,
    #[arg(
        long,
        env = "KUBERNETES_TOKEN_BROKER_POD_LABEL_SELECTOR",
        value_parser = parse_label_selector_arg,
        hide = true
    )]
    kubernetes_token_broker_pod_label_selector: Option<BTreeMap<String, String>>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_BROKER_URL")]
    session_sandbox_iron_broker_url: Option<String>,
    #[arg(long, env = "KUBERNETES_TOKEN_BROKER_URL", hide = true)]
    kubernetes_token_broker_url: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_BROKER_NAME")]
    session_sandbox_iron_broker_name: Option<String>,
    #[arg(long, env = "KUBERNETES_TOKEN_BROKER_NAME", hide = true)]
    kubernetes_token_broker_name: Option<String>,
    #[arg(long, env = "SESSION_SANDBOX_IRON_BROKER_CONFIGMAP_NAME")]
    session_sandbox_iron_broker_configmap_name: Option<String>,
    #[arg(long, env = "KUBERNETES_TOKEN_BROKER_CONFIGMAP_NAME", hide = true)]
    kubernetes_token_broker_configmap_name: Option<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum SandboxBackendKind {
    Local,
    #[value(name = "agent-k8s")]
    AgentK8s,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum SandboxWorkloadKind {
    Mock,
    #[value(name = "codex-app-server")]
    CodexAppServer,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum IronProxySecretSourceArg {
    Env,
    #[value(name = "onepassword")]
    OnePassword,
    #[value(name = "onepassword-connect")]
    OnePasswordConnect,
}

fn default_sandbox_image(workload: SandboxWorkloadKind) -> &'static str {
    match workload {
        SandboxWorkloadKind::Mock => "busybox:1.36",
        SandboxWorkloadKind::CodexAppServer => "centaur-agent:latest",
    }
}

fn agent_sandbox_config_from_args(args: &Args) -> Result<AgentSandboxConfig, ServerError> {
    let mut config = AgentSandboxConfig::new(args.session_sandbox_k8s_namespace.clone());
    config.image_pull_policy = first_nonempty([
        args.session_sandbox_image_pull_policy.as_deref(),
        args.kubernetes_agent_image_pull_policy.as_deref(),
    ]);
    config.image_pull_secrets = sandbox_image_pull_secrets_from_args(args);
    config.runtime_class_name = first_nonempty([
        args.session_sandbox_runtime_class_name.as_deref(),
        args.kubernetes_sandbox_runtime_class_name.as_deref(),
    ]);
    config.service_account_name = first_nonempty([
        args.session_sandbox_service_account_name.as_deref(),
        args.kubernetes_sandbox_service_account_name.as_deref(),
    ]);
    config.state_volume = sandbox_state_volume_from_args(args);
    config.iron_proxy = iron_proxy_config_from_args(args)?;
    Ok(config)
}

fn iron_proxy_config_from_args(args: &Args) -> Result<Option<IronProxyPodConfig>, ServerError> {
    let fragment_paths = iron_proxy_fragment_paths(args)?;
    let ca_cert_secret_name = first_nonempty([
        args.session_sandbox_iron_proxy_ca_cert_secret_name
            .as_deref(),
        args.kubernetes_firewall_ca_secret_name.as_deref(),
    ]);
    let ca_key_secret_name = first_nonempty([
        args.session_sandbox_iron_proxy_ca_key_secret_name
            .as_deref(),
        args.kubernetes_firewall_ca_key_secret_name.as_deref(),
    ]);
    if !iron_proxy_enabled(
        args.session_sandbox_iron_proxy_enabled,
        !fragment_paths.is_empty(),
        ca_cert_secret_name.is_some() && ca_key_secret_name.is_some(),
    ) {
        return Ok(None);
    }
    let image = first_nonempty([
        args.session_sandbox_iron_proxy_image.as_deref(),
        args.kubernetes_iron_proxy_image.as_deref(),
    ])
    .unwrap_or_else(|| "centaur-iron-proxy:latest".to_owned());
    let mut config = IronProxyPodConfig::new(
        image,
        ca_cert_secret_name.ok_or(ServerError::MissingIronProxyCaSecret)?,
        ca_key_secret_name.ok_or(ServerError::MissingIronProxyCaSecret)?,
    )
    .with_fragments(load_fragment_files(&fragment_paths)?);
    config.image_pull_policy = first_nonempty([
        args.session_sandbox_iron_proxy_image_pull_policy.as_deref(),
        args.kubernetes_iron_proxy_image_pull_policy.as_deref(),
        args.kubernetes_agent_image_pull_policy.as_deref(),
    ]);
    config.image_pull_secrets = sandbox_image_pull_secrets_from_args(args);
    config.source_policy = source_policy_from_args(args);
    if let Some(secret_name) = first_nonempty([
        args.session_sandbox_iron_proxy_env_secret.as_deref(),
        args.kubernetes_secret_env_name.as_deref(),
    ]) {
        config.secret_env_name = Some(secret_name.clone());
        config.secret_env_prefix = first_nonempty([
            args.session_sandbox_iron_proxy_env_secret_prefix.as_deref(),
            args.kubernetes_secret_env_prefix.as_deref(),
        ])
        .unwrap_or_default();
        config.env_from_secret_names.push(secret_name);
    }
    if matches!(config.source_policy.kind, SourceKind::OnePassword) {
        if let Some(secret_name) =
            first_nonempty([args.kubernetes_bootstrap_secret_name.as_deref()])
        {
            config.env_from_secret_names.push(secret_name);
        }
    }
    if let Some(app_name) = first_nonempty([args.kubernetes_op_connect_app_name.as_deref()]) {
        config.op_connect_app_name = app_name;
    }
    config.op_connect_port = args
        .kubernetes_op_connect_port
        .or_else(|| {
            first_nonempty([args.kubernetes_op_connect_host.as_deref()])
                .and_then(|value| parse_host_port(&value))
        })
        .unwrap_or(config.op_connect_port);
    if let Some(labels) = args
        .kubernetes_api_pod_label_selector
        .as_ref()
        .filter(|labels| !labels.is_empty())
    {
        config.api_pod_labels = labels.clone();
    }
    if let Some(labels) = args
        .session_sandbox_iron_broker_pod_label_selector
        .as_ref()
        .or(args.kubernetes_token_broker_pod_label_selector.as_ref())
        .filter(|labels| !labels.is_empty())
    {
        config.token_broker_pod_labels = labels.clone();
    }
    config.harness_auth_modes = harness_auth_modes_from_args(args);
    insert_optional_env(
        &mut config.extra_env,
        "OP_CONNECT_HOST",
        first_nonempty([
            args.session_sandbox_op_connect_host.as_deref(),
            args.kubernetes_op_connect_host.as_deref(),
        ]),
    );
    insert_optional_env(
        &mut config.extra_env,
        "IRON_BROKER_URL",
        first_nonempty([
            args.session_sandbox_iron_broker_url.as_deref(),
            args.kubernetes_token_broker_url.as_deref(),
        ]),
    );
    config.token_broker_name = first_nonempty([
        args.session_sandbox_iron_broker_name.as_deref(),
        args.kubernetes_token_broker_name.as_deref(),
    ]);
    config.token_broker_configmap_name = first_nonempty([
        args.session_sandbox_iron_broker_configmap_name.as_deref(),
        args.kubernetes_token_broker_configmap_name.as_deref(),
    ]);
    Ok(Some(config))
}

fn iron_proxy_fragment_paths(args: &Args) -> Result<Vec<PathBuf>, ServerError> {
    let mut paths = clean_paths(&args.session_sandbox_iron_proxy_fragment_paths);
    let mut dirs = clean_paths(&args.session_sandbox_iron_proxy_fragment_dirs);
    if dirs.is_empty() {
        dirs.extend(clean_paths(&args.tool_dirs));
    }
    paths.extend(discover_fragment_files(&dirs)?);
    paths.sort();
    paths.dedup();
    Ok(paths)
}

fn iron_proxy_enabled(
    explicit: Option<bool>,
    has_fragment_paths: bool,
    has_kubernetes_proxy_config: bool,
) -> bool {
    if let Some(enabled) = explicit {
        return enabled;
    }
    has_fragment_paths || has_kubernetes_proxy_config
}

fn source_policy_from_args(args: &Args) -> SourcePolicy {
    let kind = args
        .firewall_manager_secret_source
        .or(args.kubernetes_firewall_manager_secret_source)
        .unwrap_or(IronProxySecretSourceArg::Env);
    let op_vault =
        first_nonempty([args.op_vault.as_deref()]).unwrap_or_else(|| "ai-agents".to_owned());
    let ttl = first_nonempty([
        args.firewall_manager_secret_ttl.as_deref(),
        args.kubernetes_firewall_manager_secret_ttl.as_deref(),
    ])
    .unwrap_or_else(|| "10m".to_owned());
    let token_broker_ttl = first_nonempty([
        args.firewall_manager_token_broker_ttl.as_deref(),
        args.kubernetes_firewall_manager_token_broker_ttl.as_deref(),
    ])
    .unwrap_or_else(|| "1m".to_owned());

    match kind {
        IronProxySecretSourceArg::Env => SourcePolicy::env(),
        IronProxySecretSourceArg::OnePassword => SourcePolicy::onepassword(op_vault, ttl),
        IronProxySecretSourceArg::OnePasswordConnect => {
            SourcePolicy::onepassword_connect(op_vault, ttl)
        }
    }
    .with_token_broker_ttl(token_broker_ttl)
}

fn harness_auth_modes_from_args(args: &Args) -> BTreeMap<String, String> {
    let mut modes = BTreeMap::new();
    if let Some(mode) = first_nonempty([args.codex_auth_mode.as_deref()]) {
        modes.insert("codex".to_owned(), mode);
    }
    if let Some(mode) = first_nonempty([args.claude_code_auth_mode.as_deref()]) {
        modes.insert("claude-code".to_owned(), mode);
    }
    modes
}

fn insert_optional_env(envs: &mut BTreeMap<String, String>, name: &str, value: Option<String>) {
    if let Some(value) = value {
        envs.insert(name.to_owned(), value);
    }
}

fn parse_host_port(value: &str) -> Option<u16> {
    value.rsplit_once(':')?.1.parse().ok()
}

fn parse_label_selector_arg(value: &str) -> Result<BTreeMap<String, String>, String> {
    let mut labels = BTreeMap::new();
    for item in value
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
    {
        let Some((key, value)) = item.split_once('=') else {
            return Err(format!("label selector item {item:?} must be key=value"));
        };
        let key = key.trim();
        let value = value.trim();
        if key.is_empty() || value.is_empty() {
            return Err(format!("label selector item {item:?} must be key=value"));
        }
        labels.insert(key.to_owned(), value.to_owned());
    }
    Ok(labels)
}

fn parse_bool_arg(value: &str) -> Result<bool, String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => Ok(true),
        "0" | "false" | "no" | "off" => Ok(false),
        _ => Err(format!("expected boolean, got {value:?}")),
    }
}

fn sandbox_repos_path_from_args(args: &Args) -> Option<String> {
    first_nonempty([
        args.session_sandbox_repos_path.as_deref(),
        args.repos_path.as_deref(),
    ])
}

fn sandbox_image_pull_secrets_from_args(args: &Args) -> Vec<String> {
    first_nonempty_vec(
        &args.session_sandbox_image_pull_secrets,
        &args.kubernetes_sandbox_image_pull_secrets,
    )
}

fn sandbox_state_volume_from_args(args: &Args) -> Option<StateVolumeConfig> {
    let enabled = args
        .session_sandbox_state_volume_enabled
        .or(args.kubernetes_sandbox_state_volume_enabled)
        .unwrap_or(false);
    if !enabled {
        return None;
    }
    let mount_path = first_nonempty([
        args.session_sandbox_state_mount_path.as_deref(),
        args.kubernetes_sandbox_state_mount_path.as_deref(),
    ])
    .unwrap_or_else(|| "/home/agent/state".to_owned());
    let size = first_nonempty([
        args.session_sandbox_state_volume_size.as_deref(),
        args.kubernetes_sandbox_state_volume_size.as_deref(),
    ])
    .unwrap_or_else(|| "10Gi".to_owned());
    let mut config = StateVolumeConfig::new(mount_path, size);
    if let Some(storage_class_name) = first_nonempty([
        args.session_sandbox_state_volume_storage_class.as_deref(),
        args.kubernetes_sandbox_state_volume_storage_class
            .as_deref(),
    ]) {
        config = config.storage_class_name(storage_class_name);
    }
    Some(config)
}

fn first_nonempty<'a>(values: impl IntoIterator<Item = Option<&'a str>>) -> Option<String> {
    values
        .into_iter()
        .flatten()
        .map(str::trim)
        .find(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn first_nonempty_vec(primary: &[String], fallback: &[String]) -> Vec<String> {
    let primary = clean_values(primary);
    if primary.is_empty() {
        clean_values(fallback)
    } else {
        primary
    }
}

fn clean_values(values: &[String]) -> Vec<String> {
    values
        .iter()
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn clean_paths(paths: &[PathBuf]) -> Vec<PathBuf> {
    paths
        .iter()
        .filter(|path| !path.as_os_str().is_empty())
        .cloned()
        .collect()
}

fn codex_app_server_spec(
    image: &str,
    thread_key: &ThreadKey,
    env_template: &[(String, String)],
    repos_path: Option<&str>,
) -> SandboxSpec {
    let mut spec = SandboxSpec::new(image).env("CENTAUR_THREAD_KEY", thread_key.as_str());
    if let Some(repos_path) = repos_path {
        spec = spec.mount(
            Mount::new(
                MountKind::Bind {
                    source_path: repos_path.to_owned(),
                },
                SANDBOX_REPOS_MOUNT_PATH,
            )
            .read_only(),
        );
    }
    for (name, value) in env_template {
        spec = spec.env(name.clone(), value.clone());
    }
    spec
}

fn codex_app_server_env_template(args: &Args) -> Vec<(String, String)> {
    let mut envs = Vec::new();
    push_env(
        &mut envs,
        "CENTAUR_API_URL",
        args.session_sandbox_centaur_api_url
            .as_deref()
            .or(args.centaur_api_url.as_deref())
            .unwrap_or("http://api:8000")
            .to_owned(),
    );
    if let Some(api_key) = args
        .session_sandbox_centaur_api_key
        .as_deref()
        .or(args.centaur_api_key.as_deref())
    {
        push_env(&mut envs, "CENTAUR_API_KEY", api_key.to_owned());
    }
    if let Some(value) = first_nonempty([args.claude_code_auth_mode.as_deref()]) {
        push_env(&mut envs, "CLAUDE_CODE_AUTH_MODE", value);
    }
    if let Some(value) = first_nonempty([args.codex_auth_mode.as_deref()]) {
        push_env(&mut envs, "CODEX_AUTH_MODE", value);
    }

    for name in &args.session_sandbox_passthrough_env {
        if let Ok(value) = env::var(name) {
            push_env(&mut envs, name, value);
        }
    }

    envs
}

fn push_env(envs: &mut Vec<(String, String)>, name: &str, value: String) {
    if let Some((_, existing_value)) = envs
        .iter_mut()
        .find(|(existing_name, _)| existing_name == name)
    {
        *existing_value = value;
    } else {
        envs.push((name.to_owned(), value));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codex_app_server_spec_mounts_repos_path_read_only() {
        let thread_key = ThreadKey::parse("test:thread").unwrap();

        let spec = codex_app_server_spec(
            "centaur-agent:latest",
            &thread_key,
            &[("CENTAUR_API_URL".to_owned(), "http://api:8000".to_owned())],
            Some("/host/github"),
        );

        assert_eq!(spec.mounts.len(), 1);
        assert_eq!(spec.mounts[0].target_path, SANDBOX_REPOS_MOUNT_PATH);
        assert!(spec.mounts[0].read_only);
        assert_eq!(
            spec.mounts[0].kind,
            MountKind::Bind {
                source_path: "/host/github".to_owned(),
            }
        );
        assert!(
            spec.env
                .iter()
                .any(|env| { env.name == "CENTAUR_API_URL" && env.value == "http://api:8000" })
        );
    }

    #[test]
    fn codex_app_server_spec_omits_repos_mount_when_unset() {
        let thread_key = ThreadKey::parse("test:thread").unwrap();

        let spec = codex_app_server_spec("centaur-agent:latest", &thread_key, &[], None);

        assert!(spec.mounts.is_empty());
        assert!(
            spec.env
                .iter()
                .any(|env| { env.name == "CENTAUR_THREAD_KEY" && env.value == "test:thread" })
        );
    }

    #[test]
    fn iron_proxy_enables_for_stock_kubernetes_proxy_config() {
        assert!(iron_proxy_enabled(None, false, true));
        assert!(iron_proxy_enabled(None, true, false));
        assert!(!iron_proxy_enabled(None, false, false));
    }

    #[test]
    fn iron_proxy_explicit_env_overrides_auto_detection() {
        assert!(!iron_proxy_enabled(Some(false), true, true));
        assert!(iron_proxy_enabled(Some(true), false, false));
    }

    #[test]
    fn parses_bool_args_like_helm_env_values() {
        assert!(parse_bool_arg("1").unwrap());
        assert!(parse_bool_arg("yes").unwrap());
        assert!(!parse_bool_arg("0").unwrap());
        assert!(!parse_bool_arg("off").unwrap());
        assert!(parse_bool_arg("maybe").is_err());
    }

    #[test]
    fn parses_label_selector_args_strictly() {
        let labels = parse_label_selector_arg("app=api, component = worker").unwrap();

        assert_eq!(labels["app"], "api");
        assert_eq!(labels["component"], "worker");
        assert!(parse_label_selector_arg("app").is_err());
        assert!(parse_label_selector_arg("app=").is_err());
    }

    #[test]
    fn clap_drives_iron_proxy_config() {
        let args = Args::try_parse_from([
            "centaur-api-server",
            "--database-url",
            "postgresql://postgres@localhost/centaur",
            "--session-sandbox-iron-proxy-enabled",
            "yes",
            "--session-sandbox-iron-proxy-image",
            "centaur-iron-proxy:test",
            "--session-sandbox-iron-proxy-ca-cert-secret-name",
            "firewall-ca-cert",
            "--session-sandbox-iron-proxy-ca-key-secret-name",
            "firewall-ca-key",
            "--firewall-manager-secret-source",
            "onepassword-connect",
            "--op-vault",
            "engineering",
            "--firewall-manager-secret-ttl",
            "5m",
            "--firewall-manager-token-broker-ttl",
            "30s",
            "--codex-auth-mode",
            "access_token",
        ])
        .unwrap();

        let config = iron_proxy_config_from_args(&args).unwrap().unwrap();

        assert_eq!(config.image, "centaur-iron-proxy:test");
        assert_eq!(config.ca_cert_secret_name, "firewall-ca-cert");
        assert_eq!(config.ca_key_secret_name, "firewall-ca-key");
        assert!(matches!(
            config.source_policy.kind,
            SourceKind::OnePasswordConnect
        ));
        assert_eq!(config.source_policy.op_vault, "engineering");
        assert_eq!(config.source_policy.ttl, "5m");
        assert_eq!(config.source_policy.token_broker_ttl, "30s");
        assert_eq!(config.harness_auth_modes["codex"], "access_token");
    }
}

#[derive(Debug, Error)]
enum ServerError {
    #[error(
        "SESSION_SANDBOX_IRON_PROXY_CA_CERT_SECRET_NAME/KUBERNETES_FIREWALL_CA_SECRET_NAME and SESSION_SANDBOX_IRON_PROXY_CA_KEY_SECRET_NAME/KUBERNETES_FIREWALL_CA_KEY_SECRET_NAME are required when sandbox iron-proxy is enabled"
    )]
    MissingIronProxyCaSecret,
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Store(#[from] centaur_session_sqlx::SessionStoreError),
    #[error(transparent)]
    IronProxy(#[from] centaur_iron_proxy::IronProxyConfigError),
    #[error(transparent)]
    KubeConfig(#[from] kube::config::KubeconfigError),
    #[error(transparent)]
    KubeInferConfig(#[from] kube::config::InferConfigError),
    #[error(transparent)]
    Kube(#[from] kube::Error),
    #[error("{0}")]
    UnsupportedConfig(String),
}
