use centaur_sandbox_core::{SandboxId, SandboxResult};
use kube::api::{DeleteParams, ListParams};

use crate::SANDBOX_ID_LABEL;
use crate::backend::{AgentSandboxBackend, map_kube_error};
use crate::resources::{
    iron_proxy_pod_name, iron_proxy_policy_name, iron_proxy_sandbox_egress_policy_name,
    iron_proxy_service_name,
};

impl AgentSandboxBackend {
    pub(in crate::backend) async fn delete_iron_proxy_resources(
        &self,
        id: &SandboxId,
    ) -> SandboxResult<()> {
        if self.config.iron_proxy.is_none() {
            return Ok(());
        }
        let _ = self
            .pods()
            .delete(&iron_proxy_pod_name(id), &DeleteParams::default())
            .await;
        let _ = self.delete_iron_proxy_pods_for_sandbox(id).await;
        let _ = self
            .services()
            .delete(&iron_proxy_service_name(id), &DeleteParams::default())
            .await;
        for name in [
            iron_proxy_sandbox_egress_policy_name(id),
            iron_proxy_policy_name(id),
        ] {
            let _ = self
                .network_policies()
                .delete(&name, &DeleteParams::default())
                .await;
        }
        self.delete_iron_proxy_configmap(id).await
    }

    async fn delete_iron_proxy_pods_for_sandbox(&self, id: &SandboxId) -> SandboxResult<()> {
        let params = ListParams::default().labels(&format!(
            "centaur.ai/iron-proxy=true,{SANDBOX_ID_LABEL}={}",
            id.as_str()
        ));
        let pods = self
            .pods()
            .list(&params)
            .await
            .map_err(|err| map_kube_error("list iron-proxy pods", err))?;
        for pod in pods.items {
            if let Some(name) = pod.metadata.name {
                let _ = self.pods().delete(&name, &DeleteParams::default()).await;
            }
        }
        Ok(())
    }
}
