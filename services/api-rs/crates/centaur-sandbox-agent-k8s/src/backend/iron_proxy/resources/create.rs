use centaur_sandbox_core::{SandboxId, SandboxResult};
use kube::api::PostParams;

use crate::backend::{AgentSandboxBackend, map_kube_error};
use crate::config::IronProxyPodConfig;
use crate::resources::{
    ResolvedIronProxy, build_iron_proxy_network_policies, build_iron_proxy_pod,
    build_iron_proxy_service,
};

impl AgentSandboxBackend {
    pub(in crate::backend::iron_proxy::resources) async fn create_iron_proxy_service(
        &self,
        id: &SandboxId,
        resolved: &ResolvedIronProxy,
    ) -> SandboxResult<()> {
        let service = build_iron_proxy_service(id, resolved);
        self.services()
            .create(&PostParams::default(), &service)
            .await
            .map(|_| ())
            .map_err(|err| map_kube_error("create iron-proxy service", err))
    }

    pub(in crate::backend::iron_proxy::resources) async fn create_iron_proxy_pod(
        &self,
        id: &SandboxId,
        resolved: &ResolvedIronProxy,
        iron_proxy: &IronProxyPodConfig,
    ) -> SandboxResult<()> {
        let pod = build_iron_proxy_pod(id, &resolved.proxy_pod_name, iron_proxy, resolved);
        self.pods()
            .create(&PostParams::default(), &pod)
            .await
            .map(|_| ())
            .map_err(|err| map_kube_error("create iron-proxy pod", err))
    }

    pub(in crate::backend::iron_proxy::resources) async fn create_iron_proxy_network_policies(
        &self,
        id: &SandboxId,
        resolved: &ResolvedIronProxy,
        iron_proxy: &IronProxyPodConfig,
    ) -> SandboxResult<()> {
        for policy in build_iron_proxy_network_policies(id, resolved, iron_proxy) {
            self.network_policies()
                .create(&PostParams::default(), &policy)
                .await
                .map_err(|err| map_kube_error("create iron-proxy network policy", err))?;
        }
        Ok(())
    }
}
