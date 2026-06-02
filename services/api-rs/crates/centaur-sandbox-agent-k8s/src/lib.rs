//! Agent Sandbox Kubernetes backend.
//!
//! The Agent Sandbox CRD types are generated from the upstream CRD with
//! `just codegen-agent-sandbox-crd`.

use std::collections::BTreeMap;
use std::pin::Pin;
use std::time::Duration;

use async_trait::async_trait;
use centaur_sandbox_core::{
    ObservedSandbox, SandboxBackend, SandboxError, SandboxHandle, SandboxId, SandboxIo,
    SandboxResult, SandboxSpec, SandboxStatus,
};
use k8s_openapi::api::apps::v1::Deployment;
use k8s_openapi::api::core::v1::{ConfigMap, Pod, Service};
use k8s_openapi::api::networking::v1::NetworkPolicy;
use kube::api::{AttachParams, DeleteParams, ListParams, Patch, PatchParams, PostParams};
use kube::{Api, Client, Error};
use serde_json::json;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio::time::{Instant, sleep};

pub use generated::agents_x_k8s_io as crd;

mod config;
pub mod generated;
mod resources;

pub use config::{AgentSandboxConfig, IronProxyPodConfig};
use resources::*;

const BACKEND_NAME: &str = "agent-sandbox-k8s";
const MANAGED_LABEL: &str = "centaur.ai/managed";
const MANAGED_BY_LABEL: &str = "centaur.ai/managed-by";
const SANDBOX_ID_LABEL: &str = "centaur.ai/sandbox-id";
const MANAGED_BY_VALUE: &str = "api-rs";
const TOKEN_BROKER_LABEL: &str = "centaur.ai/iron-token-broker";
const TOKEN_BROKER_CONFIG_KEY: &str = "iron-token-broker.yaml";

#[derive(Clone)]
pub struct AgentSandboxBackend {
    client: Client,
    config: AgentSandboxConfig,
}

impl AgentSandboxBackend {
    pub fn new(client: Client, config: AgentSandboxConfig) -> Self {
        Self { client, config }
    }

    pub async fn try_default(namespace: impl Into<String>) -> SandboxResult<Self> {
        let client = Client::try_default()
            .await
            .map_err(|err| SandboxError::Backend(format!("create kube client: {err}")))?;
        Ok(Self::new(client, AgentSandboxConfig::new(namespace)))
    }

    fn sandboxes(&self) -> Api<crd::Sandbox> {
        Api::namespaced(self.client.clone(), &self.config.namespace)
    }

    fn pods(&self) -> Api<Pod> {
        Api::namespaced(self.client.clone(), &self.config.namespace)
    }

    fn config_maps(&self) -> Api<ConfigMap> {
        Api::namespaced(self.client.clone(), &self.config.namespace)
    }

    fn services(&self) -> Api<Service> {
        Api::namespaced(self.client.clone(), &self.config.namespace)
    }

    fn network_policies(&self) -> Api<NetworkPolicy> {
        Api::namespaced(self.client.clone(), &self.config.namespace)
    }

    fn deployments(&self) -> Api<Deployment> {
        Api::namespaced(self.client.clone(), &self.config.namespace)
    }

    async fn get_sandbox(&self, id: &SandboxId) -> SandboxResult<Option<crd::Sandbox>> {
        match self.sandboxes().get(id.as_str()).await {
            Ok(sandbox) => Ok(Some(sandbox)),
            Err(err) if is_not_found(&err) => Ok(None),
            Err(err) => Err(map_kube_error("get sandbox", err)),
        }
    }

    async fn get_pod(&self, id: &SandboxId) -> SandboxResult<Option<Pod>> {
        match self.pods().get(id.as_str()).await {
            Ok(pod) => Ok(Some(pod)),
            Err(err) if is_not_found(&err) => Ok(None),
            Err(err) => Err(map_kube_error("get sandbox pod", err)),
        }
    }

    async fn patch_replicas(&self, id: &SandboxId, replicas: i32) -> SandboxResult<()> {
        let params = PatchParams::apply(&self.config.field_manager);
        let patch = Patch::Merge(json!({ "spec": { "replicas": replicas } }));
        self.sandboxes()
            .patch(id.as_str(), &params, &patch)
            .await
            .map(|_| ())
            .map_err(|err| map_kube_error("patch sandbox replicas", err))
    }

    fn resolve_iron_proxy(
        &self,
        id: &SandboxId,
        spec: &SandboxSpec,
    ) -> SandboxResult<Option<ResolvedIronProxy>> {
        let Some(iron_proxy) = &self.config.iron_proxy else {
            return Ok(None);
        };
        let fragments = iron_proxy_fragments_for_spec(iron_proxy, spec)?;
        let config_yaml = centaur_iron_proxy::render_proxy_yaml_with_source_policy(
            None,
            &fragments,
            &iron_proxy.source_policy,
        )
        .map_err(|err| SandboxError::InvalidSpec(format!("iron-proxy config: {err}")))?;
        let placeholder_env = centaur_iron_proxy::placeholder_env(&fragments);
        let proxy_port = centaur_iron_proxy::proxy_listen_port_from_yaml(&config_yaml)
            .map_err(|err| SandboxError::InvalidSpec(format!("iron-proxy proxy port: {err}")))?;
        let listen_ports = centaur_iron_proxy::listen_ports_from_yaml(&config_yaml)
            .map_err(|err| SandboxError::InvalidSpec(format!("iron-proxy listen ports: {err}")))?;
        let proxy_host = iron_proxy_service_name(id);
        let mut pg_dsn_env = BTreeMap::new();
        let mut pg_proxy_password_env = BTreeMap::new();
        for entry in centaur_iron_proxy::pg_dsn_envs(&fragments) {
            let password = pg_proxy_password_env
                .entry(entry.password_env.clone())
                .or_insert_with(proxy_password)
                .clone();
            pg_dsn_env.entry(entry.env_name).or_insert_with(|| {
                proxied_pg_url(&proxy_host, entry.port, &password, &entry.database)
            });
        }
        Ok(Some(ResolvedIronProxy {
            config_yaml,
            placeholder_env,
            proxy_host,
            proxy_pod_name: new_iron_proxy_pod_name(id),
            proxy_port,
            listen_ports,
            pg_dsn_env,
            pg_proxy_password_env,
        }))
    }

    async fn create_iron_proxy_configmap(
        &self,
        id: &SandboxId,
        resolved: Option<&ResolvedIronProxy>,
    ) -> SandboxResult<()> {
        let Some(resolved) = resolved else {
            return Ok(());
        };
        let name = iron_proxy_configmap_name(id);
        let _ = self.delete_iron_proxy_configmap(id).await;
        let body = ConfigMap {
            metadata: object_meta(name, iron_proxy_labels(id)),
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

    async fn delete_iron_proxy_configmap(&self, id: &SandboxId) -> SandboxResult<()> {
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

    async fn reconcile_token_broker(&self, iron_proxy: &IronProxyPodConfig) -> SandboxResult<()> {
        let Some(token_broker_name) = iron_proxy.token_broker_name.as_deref() else {
            return Ok(());
        };
        let mut fragments = centaur_iron_proxy::harness_broker_fragments().map_err(|err| {
            SandboxError::InvalidSpec(format!("iron-token-broker fragments: {err}"))
        })?;
        fragments.extend(iron_proxy.fragments.clone());
        let rendered = centaur_iron_proxy::render_token_broker_yaml_with_source_policy(
            &fragments,
            &iron_proxy.source_policy,
        )
        .map_err(|err| SandboxError::InvalidSpec(format!("iron-token-broker config: {err}")))?;
        if self
            .apply_token_broker_configmap(iron_proxy, &rendered)
            .await?
        {
            self.patch_token_broker_config_hash(token_broker_name, &short_sha256(&rendered))
                .await?;
        }
        Ok(())
    }

    async fn apply_token_broker_configmap(
        &self,
        iron_proxy: &IronProxyPodConfig,
        rendered: &str,
    ) -> SandboxResult<bool> {
        let name = iron_token_broker_configmap_name(iron_proxy)?;
        let data = BTreeMap::from([(TOKEN_BROKER_CONFIG_KEY.to_owned(), rendered.to_owned())]);
        match self.config_maps().get(&name).await {
            Ok(existing) => {
                if existing
                    .data
                    .as_ref()
                    .and_then(|data| data.get(TOKEN_BROKER_CONFIG_KEY))
                    .is_some_and(|value| value == rendered)
                {
                    return Ok(false);
                }
                let patch = Patch::Merge(json!({
                    "metadata": {"labels": token_broker_labels()},
                    "data": data,
                }));
                self.config_maps()
                    .patch(&name, &PatchParams::default(), &patch)
                    .await
                    .map(|_| true)
                    .map_err(|err| map_kube_error("patch iron-token-broker configmap", err))
            }
            Err(err) if is_not_found(&err) => {
                let body = ConfigMap {
                    metadata: object_meta(name, token_broker_labels()),
                    data: Some(data),
                    ..Default::default()
                };
                self.config_maps()
                    .create(&PostParams::default(), &body)
                    .await
                    .map(|_| true)
                    .map_err(|err| map_kube_error("create iron-token-broker configmap", err))
            }
            Err(err) => Err(map_kube_error("get iron-token-broker configmap", err)),
        }
    }

    async fn patch_token_broker_config_hash(
        &self,
        token_broker_name: &str,
        config_hash: &str,
    ) -> SandboxResult<()> {
        let patch = Patch::Merge(json!({
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "centaur.ai/config-hash": config_hash,
                        },
                    },
                },
            },
        }));
        match self
            .deployments()
            .patch(token_broker_name, &PatchParams::default(), &patch)
            .await
        {
            Ok(_) => Ok(()),
            Err(err) if is_not_found(&err) => Ok(()),
            Err(err) => Err(map_kube_error("patch iron-token-broker deployment", err)),
        }
    }

    async fn create_iron_proxy_resources(
        &self,
        id: &SandboxId,
        resolved: Option<&ResolvedIronProxy>,
    ) -> SandboxResult<()> {
        let Some(resolved) = resolved else {
            return Ok(());
        };
        if let Some(iron_proxy) = &self.config.iron_proxy {
            self.reconcile_token_broker(iron_proxy).await?;
        }
        self.delete_iron_proxy_resources(id).await?;
        self.create_iron_proxy_configmap(id, Some(resolved)).await?;
        self.create_iron_proxy_service(id, resolved).await?;
        self.create_iron_proxy_network_policies(id, resolved)
            .await?;
        self.create_iron_proxy_pod(id, resolved).await?;
        self.wait_until_proxy_running(resolved).await
    }

    async fn create_iron_proxy_service(
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

    async fn create_iron_proxy_pod(
        &self,
        id: &SandboxId,
        resolved: &ResolvedIronProxy,
    ) -> SandboxResult<()> {
        let Some(iron_proxy) = &self.config.iron_proxy else {
            return Ok(());
        };
        let pod = build_iron_proxy_pod(id, &resolved.proxy_pod_name, iron_proxy, resolved);
        self.pods()
            .create(&PostParams::default(), &pod)
            .await
            .map(|_| ())
            .map_err(|err| map_kube_error("create iron-proxy pod", err))
    }

    async fn create_iron_proxy_network_policies(
        &self,
        id: &SandboxId,
        resolved: &ResolvedIronProxy,
    ) -> SandboxResult<()> {
        let Some(iron_proxy) = &self.config.iron_proxy else {
            return Ok(());
        };
        for policy in build_iron_proxy_network_policies(id, resolved, iron_proxy) {
            self.network_policies()
                .create(&PostParams::default(), &policy)
                .await
                .map_err(|err| map_kube_error("create iron-proxy network policy", err))?;
        }
        Ok(())
    }

    async fn delete_iron_proxy_resources(&self, id: &SandboxId) -> SandboxResult<()> {
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

    async fn wait_until_running(&self, id: &SandboxId) -> SandboxResult<()> {
        let deadline = Instant::now() + self.config.ready_timeout;
        loop {
            match self.status(id).await? {
                SandboxStatus::Running => return Ok(()),
                SandboxStatus::Gone | SandboxStatus::Stopped => {
                    return Err(SandboxError::NotReady(format!(
                        "sandbox {} reached terminal state before running",
                        id.as_str()
                    )));
                }
                status if Instant::now() >= deadline => {
                    return Err(SandboxError::NotReady(format!(
                        "sandbox {} did not become running before timeout; latest status: {status:?}",
                        id.as_str()
                    )));
                }
                _ => sleep(Duration::from_millis(500)).await,
            }
        }
    }

    async fn wait_until_proxy_running(&self, resolved: &ResolvedIronProxy) -> SandboxResult<()> {
        let deadline = Instant::now() + self.config.ready_timeout;
        let pod_name = &resolved.proxy_pod_name;
        loop {
            match self.pods().get(pod_name).await {
                Ok(pod) if sandbox_status_from_pod(1, Some(&pod)) == SandboxStatus::Running => {
                    return Ok(());
                }
                Ok(pod) if sandbox_status_from_pod(1, Some(&pod)) == SandboxStatus::Stopped => {
                    return Err(SandboxError::NotReady(format!(
                        "iron-proxy pod {pod_name} reached terminal state before running"
                    )));
                }
                Ok(pod) if Instant::now() >= deadline => {
                    return Err(SandboxError::NotReady(format!(
                        "iron-proxy pod {pod_name} did not become running before timeout; latest phase: {:?}",
                        pod.status.and_then(|status| status.phase)
                    )));
                }
                Ok(_) => sleep(Duration::from_millis(500)).await,
                Err(err) if is_not_found(&err) && Instant::now() < deadline => {
                    sleep(Duration::from_millis(500)).await;
                }
                Err(err) if is_not_found(&err) => {
                    return Err(SandboxError::NotReady(format!(
                        "iron-proxy pod {pod_name} was not created before timeout"
                    )));
                }
                Err(err) => return Err(map_kube_error("wait iron-proxy pod", err)),
            }
        }
    }

    async fn attach_io(&self, id: &SandboxId) -> SandboxResult<SandboxIo> {
        if self.status(id).await? != SandboxStatus::Running {
            return Err(SandboxError::NotReady(format!(
                "agent sandbox {} is not running",
                id.as_str()
            )));
        }
        let params = AttachParams::default()
            .container(self.config.container_name.clone())
            .stdin(true)
            .stdout(true)
            .stderr(true)
            .tty(false)
            .max_stdout_buf_size(1024 * 1024)
            .max_stderr_buf_size(1024 * 1024);
        let mut attached = self
            .pods()
            .attach(id.as_str(), &params)
            .await
            .map_err(|err| map_kube_error("attach sandbox pod", err))?;
        let stdin = attached
            .stdin()
            .map(|stream| Box::pin(stream) as Pin<Box<dyn AsyncWrite + Send>>);
        let stdout = attached
            .stdout()
            .map(|stream| Box::pin(stream) as Pin<Box<dyn AsyncRead + Send>>);
        let stderr = attached
            .stderr()
            .map(|stream| Box::pin(stream) as Pin<Box<dyn AsyncRead + Send>>);
        let stdin = stdin.ok_or_else(|| SandboxError::Io("stdin was not attached".to_owned()))?;
        let stdout =
            stdout.ok_or_else(|| SandboxError::Io("stdout was not attached".to_owned()))?;
        let stderr =
            stderr.ok_or_else(|| SandboxError::Io("stderr was not attached".to_owned()))?;
        // Keep kube's attach process alive as long as the returned streams are in use.
        Ok(SandboxIo::with_guard(stdin, stdout, stderr, attached))
    }
}

#[async_trait]
impl SandboxBackend for AgentSandboxBackend {
    fn name(&self) -> &'static str {
        BACKEND_NAME
    }

    async fn create(&self, spec: SandboxSpec) -> SandboxResult<SandboxHandle> {
        let id = SandboxId::new(next_sandbox_name());
        let resolved_iron_proxy = self.resolve_iron_proxy(&id, &spec)?;
        if let Err(err) = self
            .create_iron_proxy_resources(&id, resolved_iron_proxy.as_ref())
            .await
        {
            let _ = self.delete_iron_proxy_resources(&id).await;
            return Err(err);
        }
        let sandbox = build_agent_sandbox(&id, &spec, &self.config, resolved_iron_proxy.as_ref())?;
        let create_result = self
            .sandboxes()
            .create(&PostParams::default(), &sandbox)
            .await
            .map_err(|err| map_kube_error("create sandbox", err));
        if let Err(err) = create_result {
            let _ = self.delete_iron_proxy_resources(&id).await;
            return Err(err);
        }
        if let Err(err) = self.wait_until_running(&id).await {
            let _ = self.stop(&id).await;
            return Err(err);
        }
        Ok(SandboxHandle::new(id, BACKEND_NAME))
    }

    async fn open_io(&self, id: &SandboxId) -> SandboxResult<SandboxIo> {
        self.attach_io(id).await
    }

    async fn status(&self, id: &SandboxId) -> SandboxResult<SandboxStatus> {
        let Some(sandbox) = self.get_sandbox(id).await? else {
            return Ok(SandboxStatus::Gone);
        };
        let replicas = sandbox.spec.replicas.unwrap_or(1);
        let pod = self.get_pod(id).await?;
        Ok(sandbox_status_from_pod(replicas, pod.as_ref()))
    }

    async fn observe(&self, id: &SandboxId) -> SandboxResult<ObservedSandbox> {
        let status = self.status(id).await?;
        Ok(ObservedSandbox::new(id.clone(), BACKEND_NAME, status))
    }

    async fn list_observed(&self) -> SandboxResult<Vec<ObservedSandbox>> {
        let params =
            ListParams::default().labels(&format!("{MANAGED_BY_LABEL}={MANAGED_BY_VALUE}"));
        let sandboxes = self
            .sandboxes()
            .list(&params)
            .await
            .map_err(|err| map_kube_error("list sandboxes", err))?;
        let mut observed = Vec::with_capacity(sandboxes.items.len());
        for sandbox in sandboxes.items {
            let Some(name) = sandbox.metadata.name else {
                continue;
            };
            let id = SandboxId::new(name);
            observed.push(self.observe(&id).await?);
        }
        Ok(observed)
    }

    async fn stop(&self, id: &SandboxId) -> SandboxResult<()> {
        match self
            .sandboxes()
            .delete(id.as_str(), &DeleteParams::default())
            .await
        {
            Ok(_) => Ok(()),
            Err(err) if is_not_found(&err) => Ok(()),
            Err(err) => Err(map_kube_error("delete sandbox", err)),
        }?;
        self.delete_iron_proxy_resources(id).await
    }

    async fn pause(&self, id: &SandboxId) -> SandboxResult<()> {
        self.patch_replicas(id, 0).await
    }

    async fn resume(&self, id: &SandboxId) -> SandboxResult<()> {
        self.patch_replicas(id, 1).await?;
        self.wait_until_running(id).await
    }
}

fn is_not_found(err: &Error) -> bool {
    matches!(err, Error::Api(api_error) if api_error.code == 404)
}

fn map_kube_error(operation: &str, err: Error) -> SandboxError {
    if is_not_found(&err) {
        SandboxError::NotFound(operation.to_owned())
    } else {
        SandboxError::Backend(format!("{operation}: {err}"))
    }
}

#[cfg(test)]
mod tests;
