use centaur_sandbox_core::{MountKind, SandboxSpec};
use k8s_openapi::api::core::v1::{
    HostPathVolumeSource, PersistentVolumeClaimVolumeSource, Volume, VolumeMount,
};

use super::super::common::empty_dir_volume;

pub(super) fn mounts(spec: &SandboxSpec) -> (Vec<Volume>, Vec<VolumeMount>) {
    let mut volumes = Vec::with_capacity(spec.mounts.len());
    let mut mounts = Vec::with_capacity(spec.mounts.len());
    for (index, mount) in spec.mounts.iter().enumerate() {
        let name = format!("mount-{index}");
        mounts.push(VolumeMount {
            name: name.clone(),
            mount_path: mount.target_path.clone(),
            read_only: Some(mount.read_only),
            ..Default::default()
        });
        volumes.push(match &mount.kind {
            MountKind::EmptyDir => empty_dir_volume(&name),
            MountKind::NamedVolume(claim_name) => Volume {
                name,
                persistent_volume_claim: Some(PersistentVolumeClaimVolumeSource {
                    claim_name: claim_name.clone(),
                    read_only: Some(mount.read_only),
                }),
                ..Default::default()
            },
            MountKind::Bind { source_path } => Volume {
                name,
                host_path: Some(HostPathVolumeSource {
                    path: source_path.clone(),
                    ..Default::default()
                }),
                ..Default::default()
            },
        });
    }
    (volumes, mounts)
}
