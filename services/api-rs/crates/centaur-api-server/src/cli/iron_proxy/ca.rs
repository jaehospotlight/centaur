use clap::Args as ClapArgs;

use super::ServerError;

#[derive(Debug, ClapArgs)]
pub(super) struct IronProxyCaArgs {
    #[arg(
        long = "kubernetes-firewall-ca-secret-name",
        env = "KUBERNETES_FIREWALL_CA_SECRET_NAME"
    )]
    cert_secret_name: Option<String>,
    #[arg(
        long = "kubernetes-firewall-ca-key-secret-name",
        env = "KUBERNETES_FIREWALL_CA_KEY_SECRET_NAME"
    )]
    key_secret_name: Option<String>,
}

impl IronProxyCaArgs {
    pub(super) fn secrets(&self) -> Result<Option<(String, String)>, ServerError> {
        match (&self.cert_secret_name, &self.key_secret_name) {
            (None, None) => Ok(None),
            (Some(cert), Some(key)) => Ok(Some((cert.clone(), key.clone()))),
            _ => Err(ServerError::MissingIronProxyCaSecret),
        }
    }
}
