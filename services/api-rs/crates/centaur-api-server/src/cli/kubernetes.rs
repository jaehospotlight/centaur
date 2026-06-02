use std::time::Duration;

use centaur_sandbox_agent_k8s::{AgentSandboxConfig, ImagePullConfig, IronProxyPodConfig};
use clap::Args as ClapArgs;

use super::ServerError;

#[derive(Debug, ClapArgs)]
pub(super) struct KubernetesSandboxArgs {
    #[arg(
        long = "kubernetes-namespace",
        env = "KUBERNETES_NAMESPACE",
        default_value = "centaur"
    )]
    namespace: String,
    #[arg(long = "kubernetes-context", env = "KUBERNETES_CONTEXT")]
    context: Option<String>,
    #[command(flatten)]
    image_pull: KubernetesImagePullArgs,
    #[arg(
        long = "kubernetes-sandbox-ready-timeout-s",
        env = "KUBERNETES_SANDBOX_READY_TIMEOUT_S",
        default_value_t = 90
    )]
    ready_timeout_s: u64,
    #[arg(
        long = "kubernetes-sandbox-runtime-class-name",
        env = "KUBERNETES_SANDBOX_RUNTIME_CLASS_NAME"
    )]
    runtime_class_name: Option<String>,
    #[arg(
        long = "kubernetes-sandbox-service-account-name",
        env = "KUBERNETES_SANDBOX_SERVICE_ACCOUNT_NAME"
    )]
    service_account_name: Option<String>,
}

#[derive(Debug, ClapArgs)]
struct KubernetesImagePullArgs {
    #[arg(
        long = "kubernetes-agent-image-pull-policy",
        env = "KUBERNETES_AGENT_IMAGE_PULL_POLICY"
    )]
    agent_image_pull_policy: Option<String>,
    #[arg(
        long = "kubernetes-sandbox-image-pull-secrets",
        env = "KUBERNETES_SANDBOX_IMAGE_PULL_SECRETS",
        value_delimiter = ','
    )]
    image_pull_secrets: Vec<String>,
}

impl From<&KubernetesImagePullArgs> for ImagePullConfig {
    fn from(args: &KubernetesImagePullArgs) -> Self {
        Self {
            policy: args.agent_image_pull_policy.clone(),
            secrets: args.image_pull_secrets.clone(),
        }
    }
}

impl KubernetesSandboxArgs {
    pub(super) async fn client(&self) -> Result<kube::Client, ServerError> {
        if let Some(context) = self.context.as_deref() {
            let kube_config = kube::Config::from_kubeconfig(&kube::config::KubeConfigOptions {
                context: Some(context.to_owned()),
                ..kube::config::KubeConfigOptions::default()
            })
            .await?;
            return Ok(kube::Client::try_from(kube_config)?);
        }
        Ok(kube::Client::try_default().await?)
    }

    pub(super) fn image_pull_config(&self) -> ImagePullConfig {
        (&self.image_pull).into()
    }

    pub(super) fn agent_config(
        &self,
        image_pull: ImagePullConfig,
        iron_proxy: Option<IronProxyPodConfig>,
    ) -> AgentSandboxConfig {
        AgentSandboxConfig {
            image_pull,
            ready_timeout: Duration::from_secs(self.ready_timeout_s),
            runtime_class_name: self.runtime_class_name.clone(),
            service_account_name: self.service_account_name.clone(),
            iron_proxy,
            ..AgentSandboxConfig::new(&self.namespace)
        }
    }
}
