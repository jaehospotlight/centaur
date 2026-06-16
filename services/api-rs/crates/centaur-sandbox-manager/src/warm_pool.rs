use std::{sync::Arc, time::Duration};

use centaur_sandbox_core::{SandboxError, SandboxId, SandboxSpec, SandboxStatus};
use centaur_session_sqlx::{PgSessionStore, SessionStoreError};
use thiserror::Error;
use tokio::time::{MissedTickBehavior, interval};
use tracing::warn;

use crate::SandboxManager;

pub type WarmSandboxSpecFactory = Arc<dyn Fn() -> SandboxSpec + Send + Sync>;

pub struct WarmPoolConfig {
    pub target_size: usize,
    pub replenish_interval: Duration,
    pub bootstrap_iron_control_principal: Option<String>,
}

#[derive(Clone, Debug, Default)]
pub struct WarmPoolClaimOutcome {
    pub sandbox_id: Option<String>,
    pub stale: Vec<WarmPoolStaleSandbox>,
}

#[derive(Clone, Debug)]
pub struct WarmPoolStaleSandbox {
    pub sandbox_id: String,
    pub reason: WarmPoolStaleReason,
    pub detail: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WarmPoolStaleReason {
    NotFound,
    NotRunning,
}

impl WarmPoolStaleReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::NotFound => "not_found",
            Self::NotRunning => "not_running",
        }
    }

    pub fn metric_label(self) -> &'static str {
        match self {
            Self::NotFound => "stale_not_found",
            Self::NotRunning => "stale_not_running",
        }
    }
}

pub struct WarmPoolManager {
    manager: Arc<SandboxManager>,
    store: PgSessionStore,
    spec_factory: WarmSandboxSpecFactory,
    workload_key: String,
    config: WarmPoolConfig,
}

impl WarmPoolManager {
    pub fn new(
        manager: Arc<SandboxManager>,
        store: PgSessionStore,
        spec_factory: WarmSandboxSpecFactory,
        workload_key: impl Into<String>,
        config: WarmPoolConfig,
    ) -> Self {
        Self {
            manager,
            store,
            spec_factory,
            workload_key: workload_key.into(),
            config,
        }
    }

    pub fn workload_key(&self) -> &str {
        &self.workload_key
    }

    pub fn spawn_replenisher(self: Arc<Self>) {
        tokio::spawn(async move {
            let mut tick = interval(self.config.replenish_interval);
            tick.set_missed_tick_behavior(MissedTickBehavior::Delay);

            loop {
                tick.tick().await;
                if let Err(error) = self.replenish_once().await {
                    warn!(%error, "session sandbox warm pool replenishment failed");
                }
            }
        });
    }

    pub async fn claim(
        &self,
        thread_key: &str,
        iron_control_principal: Option<&str>,
    ) -> Result<WarmPoolClaimOutcome, WarmPoolError> {
        let mut stale = Vec::new();
        loop {
            let Some(sandbox_id) = self
                .store
                .claim_ready_warm_sandbox(self.workload_key.as_str(), thread_key)
                .await?
            else {
                return Ok(WarmPoolClaimOutcome {
                    sandbox_id: None,
                    stale,
                });
            };

            let id = SandboxId::new(sandbox_id.as_str());
            let (failure, stale_reason) = match self.manager.status(&id).await {
                // Only `Running` accepts `open_io`. `Created` means the
                // runtime regressed after the replenisher saw it running
                // (backends wait for readiness before returning from create),
                // so claiming it would fail at I/O attach.
                Ok(SandboxStatus::Running) => {
                    if let Some(principal_id) = iron_control_principal
                        && let Err(error) = self
                            .manager
                            .assign_iron_control_proxy_principal(&id, principal_id)
                            .await
                    {
                        let error_message = error.to_string();
                        let _ = self
                            .store
                            .mark_warm_sandbox_failed(&sandbox_id, &error_message)
                            .await;
                        return Err(WarmPoolError::Sandbox(error));
                    }
                    return Ok(WarmPoolClaimOutcome {
                        sandbox_id: Some(sandbox_id),
                        stale,
                    });
                }
                Ok(status) => (
                    format!("claimed warm sandbox was not running: {status:?}"),
                    WarmPoolStaleReason::NotRunning,
                ),
                Err(SandboxError::NotFound(_)) => (
                    "claimed warm sandbox was not found".to_owned(),
                    WarmPoolStaleReason::NotFound,
                ),
                Err(error) => {
                    let error_message = error.to_string();
                    warn!(%sandbox_id, error = %error_message);
                    let _ = self
                        .store
                        .mark_warm_sandbox_failed(&sandbox_id, &error_message)
                        .await;
                    return Err(WarmPoolError::Sandbox(error));
                }
            };
            warn!(%sandbox_id, error = %failure, thread_key);
            stale.push(WarmPoolStaleSandbox {
                sandbox_id: sandbox_id.clone(),
                reason: stale_reason,
                detail: failure.clone(),
            });
            self.store
                .mark_warm_sandbox_failed(&sandbox_id, &failure)
                .await?;
        }
    }

    async fn replenish_once(&self) -> Result<(), WarmPoolError> {
        let needed = self.config.target_size.saturating_sub(
            self.store
                .count_ready_warm_sandboxes(self.workload_key.as_str())
                .await?
                .max(0) as usize,
        );

        for _ in 0..needed {
            let mut spec = (self.spec_factory)();
            if let Some(principal_id) = &self.config.bootstrap_iron_control_principal {
                spec.iron_control_principal = Some(principal_id.clone());
            }
            let handle = self.manager.create_running(spec).await?;
            if let Err(error) = self
                .store
                .insert_ready_warm_sandbox(handle.id.as_str(), self.workload_key.as_str())
                .await
            {
                let _ = self.manager.stop(&handle.id).await;
                return Err(WarmPoolError::Store(error));
            }
        }

        Ok(())
    }
}

#[derive(Debug, Error)]
pub enum WarmPoolError {
    #[error(transparent)]
    Store(#[from] SessionStoreError),
    #[error(transparent)]
    Sandbox(#[from] SandboxError),
}
