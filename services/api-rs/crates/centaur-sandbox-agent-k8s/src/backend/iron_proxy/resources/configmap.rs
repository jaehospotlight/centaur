use std::collections::BTreeMap;

use centaur_sandbox_core::{SandboxId, SandboxResult};
use k8s_openapi::api::core::v1::ConfigMap;
use kube::api::{DeleteParams, PostParams};

use crate::backend::{AgentSandboxBackend, is_not_found, map_kube_error};
use crate::resources::{
    ResolvedIronProxy, iron_proxy_configmap_name, iron_proxy_labels, object_meta,
};

impl AgentSandboxBackend {
    pub(in crate::backend::iron_proxy::resources) async fn create_iron_proxy_configmap(
        &self,
        id: &SandboxId,
        resolved: &ResolvedIronProxy,
    ) -> SandboxResult<()> {
        let _ = self.delete_iron_proxy_configmap(id).await;
        let body = ConfigMap {
            metadata: object_meta(iron_proxy_configmap_name(id), iron_proxy_labels(id)),
            data: Some(BTreeMap::from([(
                "proxy.yaml".to_owned(),
                resolved.config_yaml.clone(),
            )])),
            ..Default::default()
        };
        self.config_maps()
            .create(&PostParams::default(), &body)
            .await
            .map(|_| ())
            .map_err(|err| map_kube_error("create iron-proxy configmap", err))
    }

    pub(in crate::backend::iron_proxy::resources) async fn delete_iron_proxy_configmap(
        &self,
        id: &SandboxId,
    ) -> SandboxResult<()> {
        if self.config.iron_proxy.is_none() {
            return Ok(());
        }
        match self
            .config_maps()
            .delete(&iron_proxy_configmap_name(id), &DeleteParams::default())
            .await
        {
            Ok(_) => Ok(()),
            Err(err) if is_not_found(&err) => Ok(()),
            Err(err) => Err(map_kube_error("delete iron-proxy configmap", err)),
        }
    }
}
