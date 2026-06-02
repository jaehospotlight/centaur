use centaur_iron_proxy::{SourceKind, SourcePolicy};
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
}

impl IronProxySourceArgs {
    pub(super) fn policy(&self) -> SourcePolicy {
        SourcePolicy {
            kind: self.source,
            op_vault: self.op_vault.clone(),
            ttl: self.secret_ttl.clone(),
            token_broker_ttl: self.token_broker_ttl.clone(),
        }
    }
}
