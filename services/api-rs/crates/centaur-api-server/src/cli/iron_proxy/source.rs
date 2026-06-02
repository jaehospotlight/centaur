use centaur_iron_proxy::{SourceKind, SourcePolicy};
use centaur_sandbox_agent_k8s::IronProxyPodConfig;
use clap::Args as ClapArgs;

#[derive(Debug, ClapArgs)]
pub(super) struct IronProxySourceArgs {
    #[arg(
        long = "kubernetes-firewall-manager-secret-source",
        env = "KUBERNETES_FIREWALL_MANAGER_SECRET_SOURCE",
        default_value = "env"
    )]
    source: SourceKind,
    #[arg(long = "op-vault", env = "OP_VAULT", default_value = "ai-agents")]
    op_vault: String,
    #[arg(
        long = "kubernetes-firewall-manager-secret-ttl",
        env = "KUBERNETES_FIREWALL_MANAGER_SECRET_TTL",
        default_value = "10m"
    )]
    secret_ttl: String,
    #[arg(
        long = "kubernetes-firewall-manager-token-broker-ttl",
        env = "KUBERNETES_FIREWALL_MANAGER_TOKEN_BROKER_TTL",
        default_value = "1m"
    )]
    token_broker_ttl: String,
    #[arg(
        long = "kubernetes-op-connect-host",
        env = "KUBERNETES_OP_CONNECT_HOST"
    )]
    op_connect_host: Option<String>,
    #[arg(
        long = "kubernetes-op-connect-app-name",
        env = "KUBERNETES_OP_CONNECT_APP_NAME"
    )]
    op_connect_app_name: Option<String>,
    #[arg(
        long = "kubernetes-op-connect-port",
        env = "KUBERNETES_OP_CONNECT_PORT"
    )]
    op_connect_port: Option<u16>,
}

impl IronProxySourceArgs {
    pub(super) fn apply_to_config(&self, config: &mut IronProxyPodConfig) {
        config.source_policy = self.policy();
        if let Some(app_name) = &self.op_connect_app_name {
            config.op_connect_app_name = app_name.clone();
        }
        config.op_connect_port = self
            .op_connect_port
            .or_else(|| self.op_connect_host.as_deref().and_then(parse_host_port))
            .unwrap_or(config.op_connect_port);
        if let Some(host) = &self.op_connect_host {
            config
                .extra_env
                .insert("OP_CONNECT_HOST".to_owned(), host.clone());
        }
    }

    pub(super) fn uses_bootstrap_secret(&self) -> bool {
        matches!(self.source, SourceKind::OnePassword)
    }

    fn policy(&self) -> SourcePolicy {
        SourcePolicy {
            kind: self.source,
            op_vault: self.op_vault.clone(),
            ttl: self.secret_ttl.clone(),
            token_broker_ttl: self.token_broker_ttl.clone(),
        }
    }
}

fn parse_host_port(value: &str) -> Option<u16> {
    value.rsplit_once(':')?.1.parse().ok()
}
