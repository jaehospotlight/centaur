use centaur_iron_proxy::SourcePolicy;
use clap::{Args as ClapArgs, ValueEnum};

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum IronProxySecretSourceArg {
    Env,
    #[value(name = "onepassword")]
    OnePassword,
    #[value(name = "onepassword-connect")]
    OnePasswordConnect,
}

#[derive(Debug, ClapArgs)]
pub(super) struct IronProxySourceArgs {
    #[arg(
        long = "kubernetes-firewall-manager-secret-source",
        env = "KUBERNETES_FIREWALL_MANAGER_SECRET_SOURCE",
        value_enum,
        default_value = "env"
    )]
    source: IronProxySecretSourceArg,
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
        match self.source {
            IronProxySecretSourceArg::Env => SourcePolicy::env(),
            IronProxySecretSourceArg::OnePassword => {
                SourcePolicy::onepassword(self.op_vault.clone(), self.secret_ttl.clone())
            }
            IronProxySecretSourceArg::OnePasswordConnect => {
                SourcePolicy::onepassword_connect(self.op_vault.clone(), self.secret_ttl.clone())
            }
        }
        .with_token_broker_ttl(self.token_broker_ttl.clone())
    }
}
