use std::time::Duration;

use centaur_sandbox_core::{SandboxError, SandboxResult, SandboxStatus};
use tokio::time::{Instant, sleep};

use crate::backend::{AgentSandboxBackend, is_not_found, map_kube_error};
use crate::resources::{ResolvedIronProxy, sandbox_status_from_pod};

impl AgentSandboxBackend {
    pub(in crate::backend::iron_proxy::resources) async fn wait_until_proxy_running(
        &self,
        resolved: &ResolvedIronProxy,
    ) -> SandboxResult<()> {
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
}
