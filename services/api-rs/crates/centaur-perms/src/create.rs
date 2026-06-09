//! `centaur-perms secrets create <type>` — register an arbitrary secret in
//! iron-control on the fly, outside the `pyproject.toml` convention.
//!
//! Every secret type is exposed as a subcommand. The credential value(s) come
//! from one of two source forms, shared across all types:
//!
//!   * `--…-ref PLACEHOLDER` resolves through the deployment's `--source-policy`
//!     (an env var name, or a 1Password item for `--source-policy onepassword*`)
//!     exactly like a tool's declared `secret_ref` would — this is the
//!     "secret source override" path (e.g. point `SLACK_BOT_TOKEN` at a
//!     `STG_SLACK_BOT_TOKEN` 1Password item).
//!   * `--…-value VALUE` stores the literal value inline, encrypted at rest in
//!     iron-control (a `control_plane` source). Use when there is no external
//!     ref to point at. Prefer feeding these from an env var rather than a
//!     literal arg to keep raw secrets out of shell history.
//!
//! After upserting, `--grant-role <FOREIGN_ID|OID>` and/or `--grant-principal
//! <THREAD_KEY|FOREIGN_ID>` optionally grant the new secret to a role and/or a
//! principal in the same call.

use std::collections::BTreeMap;

use centaur_iron_control::{
    AwsAuthSecretInput, GcpAuthSecretInput, Grantee, HmacSecretHeader, HmacSecretInput,
    InjectConfig, IronControlClient, OAuthTokenSecretInput, PgDsnSecretInput, ReplaceConfig,
    RequestRule, SecretRecord, SecretSource, StaticSecretInput, gcp_auth_scopes_or_default,
    managed_labels, source_from_placeholder,
};
use centaur_iron_proxy::SourcePolicy;
use clap::{Args, Subcommand};
use eyre::{Result, bail};

use crate::principal::resolve_principal;
use crate::{
    Cli, build_source_policy, ensure_principal, get_role_or_fail, grant_secrets, parse_kv,
};

#[derive(Subcommand, Debug)]
pub enum SecretCreateCmd {
    /// A static secret: one source, injected into the request or used to
    /// replace a tool-written placeholder token.
    Static(Box<StaticCreateArgs>),
    /// An OAuth token secret: iron-proxy mints/refreshes an access token from
    /// the named `--credential-*` sources and injects it.
    Oauth(Box<OAuthCreateArgs>),
    /// A GCP auth secret: a service-account keyfile (or workload identity) that
    /// iron-proxy exchanges for access tokens.
    Gcp(Box<GcpCreateArgs>),
    /// A Postgres DSN secret: an upstream connection string proxied per
    /// `database`.
    PgDsn(Box<PgDsnCreateArgs>),
    /// An HMAC signing secret: iron-proxy signs requests with the named
    /// `--credential-*` sources per the signature template.
    Hmac(Box<HmacCreateArgs>),
    /// An AWS auth secret: iron-proxy re-signs SigV4 requests with the resolved
    /// access key (and optional session token).
    Aws(Box<AwsCreateArgs>),
}

pub async fn run(cli: &Cli, client: &IronControlClient, cmd: &SecretCreateCmd) -> Result<()> {
    let policy = build_source_policy(cli)?;
    let (record, grant) = match cmd {
        SecretCreateCmd::Static(args) => {
            let input = args.to_input(&cli.namespace, &policy)?;
            (client.upsert_static_secret(&input).await?, &args.grant)
        }
        SecretCreateCmd::Oauth(args) => {
            let input = args.to_input(&cli.namespace, &policy)?;
            (client.upsert_oauth_token_secret(&input).await?, &args.grant)
        }
        SecretCreateCmd::Gcp(args) => {
            let input = args.to_input(&cli.namespace, &policy)?;
            (client.upsert_gcp_auth_secret(&input).await?, &args.grant)
        }
        SecretCreateCmd::PgDsn(args) => {
            let input = args.to_input(&cli.namespace, &policy)?;
            (client.upsert_pg_dsn_secret(&input).await?, &args.grant)
        }
        SecretCreateCmd::Hmac(args) => {
            let input = args.to_input(&cli.namespace, &policy)?;
            (client.upsert_hmac_secret(&input).await?, &args.grant)
        }
        SecretCreateCmd::Aws(args) => {
            let input = args.to_input(&cli.namespace, &policy)?;
            (client.upsert_aws_auth_secret(&input).await?, &args.grant)
        }
    };

    println!(
        "secret {} ({}) upserted",
        record.foreign_id.as_deref().unwrap_or("-"),
        record.id,
    );
    apply_grants(cli, client, grant, &record).await
}

/// After creating the secret, grant it directly to a role and/or a principal,
/// per `--grant-role` / `--grant-principal`. Both, either, or neither may be
/// set; a principal is created if it doesn't exist yet (as `principals grant`
/// does), so an operator can grant to a not-yet-seen principal up front.
async fn apply_grants(
    cli: &Cli,
    client: &IronControlClient,
    grant: &GrantArgs,
    record: &SecretRecord,
) -> Result<()> {
    if let Some(role_ref) = grant.grant_role.as_deref() {
        let role = get_role_or_fail(client, &cli.namespace, role_ref).await?;
        println!(
            "role: {} ({})",
            role.foreign_id.as_deref().unwrap_or("-"),
            role.id
        );
        grant_secrets(
            client,
            &Grantee::Role(role.id),
            std::slice::from_ref(&record.id),
        )
        .await?;
    }
    if let Some(principal_ref) = grant.grant_principal.as_deref() {
        let identity =
            resolve_principal(principal_ref, grant.slack_user.as_deref(), &cli.namespace);
        let principal_id = ensure_principal(client, &identity).await?;
        println!("principal: {} ({principal_id})", identity.foreign_id);
        grant_secrets(
            client,
            &Grantee::Principal(principal_id),
            std::slice::from_ref(&record.id),
        )
        .await?;
    }
    Ok(())
}

/// Optional grant targets shared by every `secrets create <type>` subcommand.
#[derive(Args, Debug)]
pub struct GrantArgs {
    /// After creating, grant the secret to this role (`foreign_id` or OID).
    #[arg(long = "grant-role", value_name = "ROLE")]
    grant_role: Option<String>,

    /// After creating, grant the secret directly to this principal: a Slack
    /// thread key (`slack:T…:C…[:ts]`, derived) or a principal `foreign_id`
    /// (e.g. `slack-channel-t1-c9`). Created if it doesn't exist yet.
    #[arg(long = "grant-principal", value_name = "PRINCIPAL")]
    grant_principal: Option<String>,

    /// Acting Slack user id, used only to key a DM principal from a
    /// `--grant-principal` thread key.
    #[arg(long = "slack-user", value_name = "ID")]
    slack_user: Option<String>,
}

// ---------------------------------------------------------------------------
// Shared source / argument helpers
// ---------------------------------------------------------------------------

/// A single credential source: exactly one of `--…-ref` (resolved via the
/// source policy) or `--…-value` (stored inline, encrypted). Flattened under a
/// type-specific prefix via `#[command(flatten)]`.
#[derive(Args, Debug)]
pub struct SourceSpec {
    /// Resolve the value from a placeholder via `--source-policy` (an env var
    /// name, or a 1Password item for `--source-policy onepassword*`).
    #[arg(long = "source-ref", value_name = "PLACEHOLDER")]
    source_ref: Option<String>,

    /// Store this literal value inline, encrypted at rest in iron-control.
    #[arg(long = "source-value", value_name = "VALUE")]
    source_value: Option<String>,
}

impl SourceSpec {
    fn resolve(&self, policy: &SourcePolicy) -> Result<SecretSource> {
        resolve_source(
            policy,
            self.source_ref.as_deref(),
            self.source_value.as_deref(),
            "--source-ref/--source-value",
        )?
        .ok_or_else(|| eyre::eyre!("a source is required: pass --source-ref or --source-value"))
    }
}

/// Resolve a `(ref, value)` pair into a source. `None` when neither is set so
/// callers can treat the source as optional (e.g. an AWS session token).
fn resolve_source(
    policy: &SourcePolicy,
    secret_ref: Option<&str>,
    value: Option<&str>,
    flags: &str,
) -> Result<Option<SecretSource>> {
    match (secret_ref, value) {
        (Some(_), Some(_)) => bail!("{flags}: pass only one"),
        (Some(r), None) => Ok(Some(source_from_placeholder(policy, r, None))),
        (None, Some(v)) => Ok(Some(SecretSource::control_plane(v))),
        (None, None) => Ok(None),
    }
}

/// Parse repeatable `--credential-ref NAME=PLACEHOLDER` / `--credential-value
/// NAME=VALUE` flags into a `name -> source` map, erroring on a duplicate name.
fn parse_credentials(
    policy: &SourcePolicy,
    refs: &[String],
    values: &[String],
) -> Result<BTreeMap<String, SecretSource>> {
    let mut out = BTreeMap::new();
    for raw in refs {
        let (name, placeholder) = parse_kv(raw, "--credential-ref")?;
        insert_unique(
            &mut out,
            name,
            source_from_placeholder(policy, &placeholder, None),
        )?;
    }
    for raw in values {
        let (name, value) = parse_kv(raw, "--credential-value")?;
        insert_unique(&mut out, name, SecretSource::control_plane(value))?;
    }
    Ok(out)
}

fn insert_unique(
    map: &mut BTreeMap<String, SecretSource>,
    name: String,
    source: SecretSource,
) -> Result<()> {
    if map.insert(name.clone(), source).is_some() {
        bail!("credential {name:?} specified more than once");
    }
    Ok(())
}

fn rules_from_hosts(hosts: &[String]) -> Vec<RequestRule> {
    hosts.iter().map(RequestRule::host).collect()
}

// ---------------------------------------------------------------------------
// static
// ---------------------------------------------------------------------------

#[derive(Args, Debug)]
pub struct StaticCreateArgs {
    /// Stable upsert key for the secret.
    #[arg(long)]
    foreign_id: String,

    /// Human-readable name.
    #[arg(long)]
    name: String,

    /// Human-readable description.
    #[arg(long)]
    description: Option<String>,

    #[command(flatten)]
    source: SourceSpec,

    /// Inject mode: add the credential as this request header (e.g.
    /// `Authorization`). Mutually exclusive with `--inject-query-param` /
    /// `--replace`.
    #[arg(long)]
    inject_header: Option<String>,

    /// Inject mode: add the credential as this query parameter.
    #[arg(long)]
    inject_query_param: Option<String>,

    /// Inject mode: Go template formatting the injected value, where `.Value`
    /// is the resolved credential (e.g. `Bearer {{.Value}}`).
    #[arg(long)]
    inject_formatter: Option<String>,

    /// Replace mode: the placeholder token the tool writes that iron-proxy
    /// swaps for the resolved credential. Mutually exclusive with `--inject-*`.
    #[arg(long)]
    replace: Option<String>,

    /// Restrict the secret to requests to this host. Repeatable.
    #[arg(long = "host", value_name = "HOST")]
    hosts: Vec<String>,

    #[command(flatten)]
    grant: GrantArgs,
}

impl StaticCreateArgs {
    fn to_input(&self, namespace: &str, policy: &SourcePolicy) -> Result<StaticSecretInput> {
        let (inject_config, replace_config) = self.injection()?;
        Ok(StaticSecretInput {
            namespace: namespace.to_owned(),
            foreign_id: self.foreign_id.clone(),
            name: self.name.clone(),
            description: self.description.clone(),
            labels: managed_labels(),
            inject_config,
            replace_config,
            source: self.source.resolve(policy)?,
            rules: rules_from_hosts(&self.hosts),
        })
    }

    /// iron-control requires exactly one of inject/replace on a static secret.
    fn injection(&self) -> Result<(Option<InjectConfig>, Option<ReplaceConfig>)> {
        let inject = self.inject_header.is_some() || self.inject_query_param.is_some();
        match (inject, &self.replace) {
            (true, Some(_)) => {
                bail!("pass either --inject-header/--inject-query-param or --replace, not both")
            }
            (false, None) => bail!(
                "a static secret needs one of --inject-header, --inject-query-param, or --replace"
            ),
            (true, None) => Ok((
                Some(InjectConfig {
                    header: self.inject_header.clone(),
                    query_param: self.inject_query_param.clone(),
                    formatter: self.inject_formatter.clone(),
                }),
                None,
            )),
            (false, Some(proxy_value)) => {
                if self.inject_formatter.is_some() {
                    bail!("--inject-formatter only applies to inject mode");
                }
                Ok((
                    None,
                    Some(ReplaceConfig {
                        proxy_value: proxy_value.clone(),
                        match_headers: Vec::new(),
                        match_body: false,
                        match_path: false,
                        match_query: false,
                        require: false,
                    }),
                ))
            }
        }
    }
}

// ---------------------------------------------------------------------------
// oauth
// ---------------------------------------------------------------------------

#[derive(Args, Debug)]
pub struct OAuthCreateArgs {
    /// Stable upsert key for the secret.
    #[arg(long)]
    foreign_id: String,

    /// Human-readable name.
    #[arg(long)]
    name: String,

    /// OAuth grant type (e.g. `client_credentials`, `refresh_token`).
    #[arg(long = "grant-type")]
    grant_type: String,

    /// OAuth token endpoint to exchange against.
    #[arg(long)]
    token_endpoint: Option<String>,

    /// OAuth scope to request. Repeatable.
    #[arg(long = "scope", value_name = "SCOPE")]
    scopes: Vec<String>,

    /// OAuth audience.
    #[arg(long)]
    audience: Option<String>,

    /// Credential resolved via the source policy: `--credential-ref
    /// NAME=PLACEHOLDER` (e.g. `client_id=OPENAI_CLIENT_ID`). Repeatable.
    #[arg(long = "credential-ref", value_name = "NAME=PLACEHOLDER")]
    credential_refs: Vec<String>,

    /// Credential stored inline, encrypted: `--credential-value NAME=VALUE`.
    /// Repeatable.
    #[arg(long = "credential-value", value_name = "NAME=VALUE")]
    credential_values: Vec<String>,

    /// Token-endpoint header sourced via the source policy:
    /// `--token-header-ref NAME=PLACEHOLDER`. Repeatable.
    #[arg(long = "token-header-ref", value_name = "NAME=PLACEHOLDER")]
    token_header_refs: Vec<String>,

    /// Token-endpoint header stored inline, encrypted: `--token-header-value
    /// NAME=VALUE`. Repeatable.
    #[arg(long = "token-header-value", value_name = "NAME=VALUE")]
    token_header_values: Vec<String>,

    /// Restrict the secret to requests to this host. Repeatable.
    #[arg(long = "host", value_name = "HOST")]
    hosts: Vec<String>,

    #[command(flatten)]
    grant: GrantArgs,
}

impl OAuthCreateArgs {
    fn to_input(&self, namespace: &str, policy: &SourcePolicy) -> Result<OAuthTokenSecretInput> {
        let credentials =
            parse_credentials(policy, &self.credential_refs, &self.credential_values)?;
        if credentials.is_empty() {
            bail!("an OAuth secret needs at least one --credential-ref/--credential-value");
        }
        let token_endpoint_headers =
            parse_credentials(policy, &self.token_header_refs, &self.token_header_values)?;
        Ok(OAuthTokenSecretInput {
            namespace: namespace.to_owned(),
            foreign_id: self.foreign_id.clone(),
            name: self.name.clone(),
            grant: self.grant_type.clone(),
            token_endpoint: self.token_endpoint.clone(),
            scopes: self.scopes.clone(),
            audience: self.audience.clone(),
            credentials,
            token_endpoint_headers,
            rules: rules_from_hosts(&self.hosts),
        })
    }
}

// ---------------------------------------------------------------------------
// gcp
// ---------------------------------------------------------------------------

#[derive(Args, Debug)]
pub struct GcpCreateArgs {
    /// Stable upsert key for the secret.
    #[arg(long)]
    foreign_id: String,

    /// Human-readable name.
    #[arg(long)]
    name: Option<String>,

    /// OAuth scope to request. Repeatable; defaults to the GCP cloud-platform
    /// scope when omitted.
    #[arg(long = "scope", value_name = "SCOPE")]
    scopes: Vec<String>,

    /// Subject to impersonate (domain-wide delegation).
    #[arg(long)]
    subject: Option<String>,

    /// The service-account keyfile source (its JSON contents).
    #[command(flatten)]
    keyfile: SourceSpec,

    /// Restrict the secret to requests to this host. Repeatable.
    #[arg(long = "host", value_name = "HOST")]
    hosts: Vec<String>,

    #[command(flatten)]
    grant: GrantArgs,
}

impl GcpCreateArgs {
    fn to_input(&self, namespace: &str, policy: &SourcePolicy) -> Result<GcpAuthSecretInput> {
        Ok(GcpAuthSecretInput {
            namespace: namespace.to_owned(),
            foreign_id: Some(self.foreign_id.clone()),
            name: self.name.clone(),
            scopes: gcp_auth_scopes_or_default(self.scopes.clone()),
            subject: self.subject.clone(),
            keyfile: Some(self.keyfile.resolve(policy)?),
            credentials_provider: None,
            rules: rules_from_hosts(&self.hosts),
        })
    }
}

// ---------------------------------------------------------------------------
// pg_dsn
// ---------------------------------------------------------------------------

#[derive(Args, Debug)]
pub struct PgDsnCreateArgs {
    /// Stable upsert key for the secret.
    #[arg(long)]
    foreign_id: String,

    /// Human-readable name.
    #[arg(long)]
    name: String,

    /// Database name to connect to on the proxied and upstream connection.
    #[arg(long)]
    database: String,

    /// Optional Postgres role to `SET ROLE` for.
    #[arg(long)]
    role: Option<String>,

    /// Human-readable description.
    #[arg(long)]
    description: Option<String>,

    /// The upstream DSN connection string source.
    #[command(flatten)]
    dsn: SourceSpec,

    #[command(flatten)]
    grant: GrantArgs,
}

impl PgDsnCreateArgs {
    fn to_input(&self, namespace: &str, policy: &SourcePolicy) -> Result<PgDsnSecretInput> {
        Ok(PgDsnSecretInput {
            namespace: namespace.to_owned(),
            foreign_id: self.foreign_id.clone(),
            name: self.name.clone(),
            database: self.database.clone(),
            description: self.description.clone(),
            role: self.role.clone(),
            labels: managed_labels(),
            dsn: self.dsn.resolve(policy)?,
        })
    }
}

// ---------------------------------------------------------------------------
// hmac
// ---------------------------------------------------------------------------

#[derive(Args, Debug)]
pub struct HmacCreateArgs {
    /// Stable upsert key for the secret.
    #[arg(long)]
    foreign_id: String,

    /// Human-readable name.
    #[arg(long)]
    name: String,

    /// Human-readable description.
    #[arg(long)]
    description: Option<String>,

    /// Go time layout for the `.Timestamp` template value.
    #[arg(long)]
    timestamp_format: String,

    /// HMAC algorithm (e.g. `sha256`).
    #[arg(long)]
    signature_algorithm: String,

    /// How the signing key is decoded (e.g. `hex`, `base64`, `utf8`).
    #[arg(long)]
    signature_key_encoding: String,

    /// How the digest is encoded onto the request (e.g. `hex`, `base64`).
    #[arg(long)]
    signature_output_encoding: String,

    /// Go template for the message to sign (over `.Timestamp`, `.Signature`,
    /// `.Credentials.<name>`).
    #[arg(long)]
    signature_message: String,

    /// Allow buffering a chunked body to sign it.
    #[arg(long)]
    allow_chunked_body: bool,

    /// Header iron-proxy writes onto the signed request, value a Go template:
    /// `--header NAME=TEMPLATE`. Repeatable.
    #[arg(long = "header", value_name = "NAME=TEMPLATE")]
    headers: Vec<String>,

    /// Signing credential resolved via the source policy: `--credential-ref
    /// NAME=PLACEHOLDER`. The key named `secret` is the HMAC key. Repeatable.
    #[arg(long = "credential-ref", value_name = "NAME=PLACEHOLDER")]
    credential_refs: Vec<String>,

    /// Signing credential stored inline, encrypted: `--credential-value
    /// NAME=VALUE`. Repeatable.
    #[arg(long = "credential-value", value_name = "NAME=VALUE")]
    credential_values: Vec<String>,

    /// Restrict the secret to requests to this host. Repeatable.
    #[arg(long = "host", value_name = "HOST")]
    hosts: Vec<String>,

    #[command(flatten)]
    grant: GrantArgs,
}

impl HmacCreateArgs {
    fn to_input(&self, namespace: &str, policy: &SourcePolicy) -> Result<HmacSecretInput> {
        let credentials =
            parse_credentials(policy, &self.credential_refs, &self.credential_values)?;
        if credentials.is_empty() {
            bail!("an HMAC secret needs at least one --credential-ref/--credential-value");
        }
        let headers = self
            .headers
            .iter()
            .map(|raw| {
                let (name, value) = parse_kv(raw, "--header")?;
                Ok(HmacSecretHeader { name, value })
            })
            .collect::<Result<Vec<_>>>()?;
        Ok(HmacSecretInput {
            namespace: namespace.to_owned(),
            foreign_id: self.foreign_id.clone(),
            name: self.name.clone(),
            description: self.description.clone(),
            labels: managed_labels(),
            timestamp_format: self.timestamp_format.clone(),
            signature_algorithm: self.signature_algorithm.clone(),
            signature_key_encoding: self.signature_key_encoding.clone(),
            signature_output_encoding: self.signature_output_encoding.clone(),
            signature_message: self.signature_message.clone(),
            allow_chunked_body: self.allow_chunked_body,
            headers,
            credentials,
            rules: rules_from_hosts(&self.hosts),
        })
    }
}

// ---------------------------------------------------------------------------
// aws_auth
// ---------------------------------------------------------------------------

#[derive(Args, Debug)]
pub struct AwsCreateArgs {
    /// Stable upsert key for the secret.
    #[arg(long)]
    foreign_id: String,

    /// Human-readable name.
    #[arg(long)]
    name: Option<String>,

    /// Human-readable description.
    #[arg(long)]
    description: Option<String>,

    /// AWS access key id, resolved via the source policy.
    #[arg(long = "access-key-id-ref", value_name = "PLACEHOLDER")]
    access_key_id_ref: Option<String>,

    /// AWS access key id, stored inline (encrypted).
    #[arg(long = "access-key-id-value", value_name = "VALUE")]
    access_key_id_value: Option<String>,

    /// AWS secret access key, resolved via the source policy.
    #[arg(long = "secret-access-key-ref", value_name = "PLACEHOLDER")]
    secret_access_key_ref: Option<String>,

    /// AWS secret access key, stored inline (encrypted).
    #[arg(long = "secret-access-key-value", value_name = "VALUE")]
    secret_access_key_value: Option<String>,

    /// AWS STS session token, resolved via the source policy. Optional.
    #[arg(long = "session-token-ref", value_name = "PLACEHOLDER")]
    session_token_ref: Option<String>,

    /// AWS STS session token, stored inline (encrypted). Optional.
    #[arg(long = "session-token-value", value_name = "VALUE")]
    session_token_value: Option<String>,

    /// Region the proxy may sign for (empty = unscoped). Repeatable.
    #[arg(long = "allowed-region", value_name = "REGION")]
    allowed_regions: Vec<String>,

    /// Service the proxy may sign for (empty = unscoped). Repeatable.
    #[arg(long = "allowed-service", value_name = "SERVICE")]
    allowed_services: Vec<String>,

    /// Restrict the secret to requests to this host. Repeatable.
    #[arg(long = "host", value_name = "HOST")]
    hosts: Vec<String>,

    #[command(flatten)]
    grant: GrantArgs,
}

impl AwsCreateArgs {
    fn to_input(&self, namespace: &str, policy: &SourcePolicy) -> Result<AwsAuthSecretInput> {
        let access_key_id = resolve_source(
            policy,
            self.access_key_id_ref.as_deref(),
            self.access_key_id_value.as_deref(),
            "--access-key-id-ref/--access-key-id-value",
        )?
        .ok_or_else(|| eyre::eyre!("--access-key-id-ref or --access-key-id-value is required"))?;
        let secret_access_key = resolve_source(
            policy,
            self.secret_access_key_ref.as_deref(),
            self.secret_access_key_value.as_deref(),
            "--secret-access-key-ref/--secret-access-key-value",
        )?
        .ok_or_else(|| {
            eyre::eyre!("--secret-access-key-ref or --secret-access-key-value is required")
        })?;
        let session_token = resolve_source(
            policy,
            self.session_token_ref.as_deref(),
            self.session_token_value.as_deref(),
            "--session-token-ref/--session-token-value",
        )?;
        Ok(AwsAuthSecretInput {
            namespace: namespace.to_owned(),
            foreign_id: self.foreign_id.clone(),
            name: self.name.clone(),
            description: self.description.clone(),
            labels: managed_labels(),
            access_key_id,
            secret_access_key,
            session_token,
            allowed_regions: self.allowed_regions.clone(),
            allowed_services: self.allowed_services.clone(),
            rules: rules_from_hosts(&self.hosts),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    fn env_policy() -> SourcePolicy {
        SourcePolicy::env()
    }

    fn op_policy() -> SourcePolicy {
        SourcePolicy::onepassword("staging", "10m")
    }

    /// A `--source-ref` resolves through the source policy exactly like a tool's
    /// declared `secret_ref` — the "point SLACK_BOT_TOKEN at a staging item" case.
    #[test]
    fn source_ref_resolves_via_policy() {
        let env = resolve_source(&env_policy(), Some("STG_SLACK_BOT_TOKEN"), None, "x")
            .unwrap()
            .unwrap();
        assert_eq!(env.source_type, "env");
        assert_eq!(env.config["var"], "STG_SLACK_BOT_TOKEN");
        assert!(env.secret.is_none());

        let op = resolve_source(&op_policy(), Some("STG_SLACK_BOT_TOKEN"), None, "x")
            .unwrap()
            .unwrap();
        assert_eq!(op.source_type, "1password");
        assert_eq!(
            op.config["secret_ref"],
            "op://staging/STG_SLACK_BOT_TOKEN/credential"
        );
    }

    /// A `--source-value` is stored inline (encrypted at rest), never resolved.
    #[test]
    fn source_value_is_inline_control_plane() {
        let src = resolve_source(&env_policy(), None, Some("xoxb-raw"), "x")
            .unwrap()
            .unwrap();
        assert_eq!(src.source_type, "control_plane");
        assert_eq!(src.secret.as_deref(), Some("xoxb-raw"));
        assert!(src.config.is_null());
    }

    #[test]
    fn source_rejects_both_and_allows_neither_optional() {
        assert!(resolve_source(&env_policy(), Some("A"), Some("b"), "x").is_err());
        assert!(
            resolve_source(&env_policy(), None, None, "x")
                .unwrap()
                .is_none()
        );
    }

    #[test]
    fn parse_credentials_mixes_refs_and_values_and_rejects_dupes() {
        let map = parse_credentials(
            &env_policy(),
            &["client_id=OPENAI_CLIENT_ID".to_owned()],
            &["client_secret=sk-1".to_owned()],
        )
        .unwrap();
        assert_eq!(map["client_id"].source_type, "env");
        assert_eq!(map["client_secret"].source_type, "control_plane");
        assert_eq!(map["client_secret"].secret.as_deref(), Some("sk-1"));

        let dupe = parse_credentials(
            &env_policy(),
            &["api_key=A".to_owned()],
            &["api_key=raw".to_owned()],
        );
        assert!(dupe.is_err());
    }

    fn static_args() -> StaticCreateArgs {
        StaticCreateArgs {
            foreign_id: "stg-slack-bot-token".to_owned(),
            name: "Staging Slack bot token".to_owned(),
            description: None,
            source: SourceSpec {
                source_ref: Some("STG_SLACK_BOT_TOKEN".to_owned()),
                source_value: None,
            },
            inject_header: None,
            inject_query_param: None,
            inject_formatter: None,
            replace: None,
            hosts: Vec::new(),
            grant: GrantArgs {
                grant_role: None,
                grant_principal: None,
                slack_user: None,
            },
        }
    }

    #[test]
    fn static_requires_exactly_one_injection_mode() {
        // neither inject nor replace
        assert!(static_args().injection().is_err());

        // both inject and replace
        let mut both = static_args();
        both.inject_header = Some("Authorization".to_owned());
        both.replace = Some("PLACEHOLDER".to_owned());
        assert!(both.injection().is_err());

        // formatter is meaningless in replace mode
        let mut bad_replace = static_args();
        bad_replace.replace = Some("PLACEHOLDER".to_owned());
        bad_replace.inject_formatter = Some("Bearer {{.Value}}".to_owned());
        assert!(bad_replace.injection().is_err());
    }

    #[test]
    fn static_inject_builds_full_input() {
        let mut args = static_args();
        args.inject_header = Some("Authorization".to_owned());
        args.inject_formatter = Some("Bearer {{.Value}}".to_owned());
        args.hosts = vec!["slack.com".to_owned()];

        let input = args.to_input("default", &op_policy()).unwrap();
        assert_eq!(input.foreign_id, "stg-slack-bot-token");
        assert_eq!(input.source.source_type, "1password");
        assert_eq!(
            input.source.config["secret_ref"],
            "op://staging/STG_SLACK_BOT_TOKEN/credential"
        );
        let inject = input.inject_config.expect("inject config");
        assert_eq!(inject.header.as_deref(), Some("Authorization"));
        assert_eq!(inject.formatter.as_deref(), Some("Bearer {{.Value}}"));
        assert!(input.replace_config.is_none());
        assert_eq!(input.rules.len(), 1);
        assert_eq!(input.rules[0].host.as_deref(), Some("slack.com"));
        // Created secrets are tagged so `secrets list --managed` finds them.
        assert_eq!(
            input.labels.get("managed-by").map(String::as_str),
            Some("centaur")
        );
    }

    #[test]
    fn oauth_requires_a_credential() {
        let args = OAuthCreateArgs {
            foreign_id: "fid".to_owned(),
            name: "n".to_owned(),
            grant_type: "client_credentials".to_owned(),
            token_endpoint: None,
            scopes: Vec::new(),
            audience: None,
            credential_refs: Vec::new(),
            credential_values: Vec::new(),
            token_header_refs: Vec::new(),
            token_header_values: Vec::new(),
            hosts: Vec::new(),
            grant: GrantArgs {
                grant_role: None,
                grant_principal: None,
                slack_user: None,
            },
        };
        assert!(args.to_input("default", &env_policy()).is_err());
    }

    #[test]
    fn aws_session_token_is_optional() {
        let args = AwsCreateArgs {
            foreign_id: "fid".to_owned(),
            name: None,
            description: None,
            access_key_id_ref: Some("AWS_ACCESS_KEY_ID".to_owned()),
            access_key_id_value: None,
            secret_access_key_ref: Some("AWS_SECRET_ACCESS_KEY".to_owned()),
            secret_access_key_value: None,
            session_token_ref: None,
            session_token_value: None,
            allowed_regions: Vec::new(),
            allowed_services: Vec::new(),
            hosts: Vec::new(),
            grant: GrantArgs {
                grant_role: None,
                grant_principal: None,
                slack_user: None,
            },
        };
        let input = args.to_input("default", &env_policy()).unwrap();
        assert_eq!(input.access_key_id.config["var"], "AWS_ACCESS_KEY_ID");
        assert!(input.session_token.is_none());
    }

    /// clap's own invariants for the whole arg tree, including `secrets create`.
    #[test]
    fn cli_definition_is_valid() {
        Cli::command().debug_assert();
    }
}
