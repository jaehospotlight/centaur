mod cleanup;
mod configmap;
mod create;
mod wait;

use centaur_sandbox_core::{SandboxId, SandboxResult};

use super::super::AgentSandboxBackend;
use crate::resources::ResolvedIronProxy;

impl AgentSandboxBackend {
    pub(in crate::backend) async fn create_iron_proxy_resources(
        &self,
        id: &SandboxId,
        resolved: Option<&ResolvedIronProxy>,
    ) -> SandboxResult<()> {
        let (Some(resolved), Some(iron_proxy)) = (resolved, self.config.iron_proxy.as_ref()) else {
            return Ok(());
        };
        self.reconcile_token_broker(iron_proxy).await?;
        self.delete_iron_proxy_resources(id).await?;
        self.create_iron_proxy_configmap(id, resolved).await?;
        self.create_iron_proxy_service(id, resolved).await?;
        self.create_iron_proxy_network_policies(id, resolved, iron_proxy)
            .await?;
        self.create_iron_proxy_pod(id, resolved, iron_proxy).await?;
        self.wait_until_proxy_running(resolved).await
    }
}
