use centaur_sandbox_agent_k8s::ImagePullConfig;
use clap::Args as ClapArgs;

#[derive(Debug, ClapArgs)]
pub(super) struct IronProxyImageArgs {
    #[arg(
        long = "kubernetes-iron-proxy-image",
        env = "KUBERNETES_IRON_PROXY_IMAGE",
        default_value = "centaur-iron-proxy:latest"
    )]
    pub(super) image_name: String,
    #[arg(
        long = "kubernetes-iron-proxy-image-pull-policy",
        env = "KUBERNETES_IRON_PROXY_IMAGE_PULL_POLICY"
    )]
    pull_policy: Option<String>,
}

impl IronProxyImageArgs {
    pub(super) fn image_pull_config(&self, fallback: &ImagePullConfig) -> ImagePullConfig {
        ImagePullConfig {
            policy: self.pull_policy.clone().or_else(|| fallback.policy.clone()),
            secrets: fallback.secrets.clone(),
        }
    }
}
