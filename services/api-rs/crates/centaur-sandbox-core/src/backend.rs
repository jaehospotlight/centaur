use async_trait::async_trait;
use bytes::Bytes;

use crate::{
    ObservedSandbox, ReadOptions, ReadResult, SandboxHandle, SandboxId, SandboxResult, SandboxSpec,
    SandboxStatus, WriteAck,
};

#[async_trait]
/// Backend-neutral lifecycle and byte-I/O operations for one sandbox runtime.
///
/// This trait intentionally models only the isolated workload primitive. Higher
/// layers decide why the sandbox exists and how stdin/stdout bytes should be
/// framed.
pub trait SandboxBackend: Send + Sync {
    /// Stable backend name used in handles, observations, and diagnostics.
    fn name(&self) -> &'static str;

    /// Create a sandbox from the supplied workload spec and return its handle.
    async fn create(&self, spec: SandboxSpec) -> SandboxResult<SandboxHandle>;

    /// Read raw bytes from the sandbox stdout or stderr stream.
    async fn read_bytes(&self, id: &SandboxId, opts: ReadOptions) -> SandboxResult<ReadResult>;

    /// Write raw bytes to the sandbox stdin stream.
    async fn write_bytes(&self, id: &SandboxId, bytes: Bytes) -> SandboxResult<WriteAck>;

    /// Close stdin without stopping the sandbox process or deleting runtime state.
    async fn close_stdin(&self, id: &SandboxId) -> SandboxResult<()>;

    /// Return the portable, cheap lifecycle status for a sandbox.
    async fn status(&self, id: &SandboxId) -> SandboxResult<SandboxStatus>;

    /// Return the full observed runtime snapshot for one sandbox.
    ///
    /// Unlike [`SandboxBackend::status`], this can include backend-owned
    /// diagnostic context used by reconcilers.
    async fn observe(&self, id: &SandboxId) -> SandboxResult<ObservedSandbox>;

    /// List all sandbox observations owned by this backend/control plane.
    async fn list_observed(&self) -> SandboxResult<Vec<ObservedSandbox>>;

    /// Stop the sandbox and clean up backend-owned runtime resources.
    async fn stop(&self, id: &SandboxId) -> SandboxResult<()>;

    /// Suspend the sandbox while preserving any backend-supported runtime state.
    async fn pause(&self, id: &SandboxId) -> SandboxResult<()>;

    /// Resume a previously suspended sandbox and wait until it can serve I/O.
    async fn resume(&self, id: &SandboxId) -> SandboxResult<()>;
}
