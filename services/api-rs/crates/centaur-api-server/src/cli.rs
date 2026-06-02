use std::net::SocketAddr;

use clap::Parser;

mod auth;
mod error;
mod iron_proxy;
mod kubernetes;
mod sandbox;
mod workload;

pub(crate) use error::ServerError;
pub(crate) use sandbox::SandboxArgs;

#[derive(Debug, Parser)]
#[command(about = "Run the Centaur API Rust control plane")]
pub(crate) struct Cli {
    #[arg(long, env = "DATABASE_URL")]
    pub(crate) database_url: String,
    #[arg(long, env = "BIND_ADDR", default_value = "127.0.0.1:8080")]
    pub(crate) bind_addr: SocketAddr,
    #[arg(long, env = "RUN_MIGRATIONS", default_value_t = false)]
    pub(crate) run_migrations: bool,
    #[command(flatten)]
    pub(crate) sandbox: SandboxArgs,
}
