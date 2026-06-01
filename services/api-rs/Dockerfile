# syntax=docker/dockerfile:1.7

FROM rust:1-slim-bookworm AS builder

WORKDIR /app/services/api-rs

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      libssl-dev \
      pkg-config

COPY services/api-rs/Cargo.toml services/api-rs/Cargo.lock ./
COPY services/api-rs/crates ./crates

# centaur-iron-proxy embeds the base config and harness fragments at compile time.
COPY services/api/api/iron-proxy.base.yaml /app/services/api/api/iron-proxy.base.yaml
COPY services/iron-proxy /app/services/iron-proxy

RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,target=/app/services/api-rs/target,sharing=locked \
    cargo build --release --locked -p centaur-api-server -p centaur-session-cli \
    && cp target/release/centaur-api-server /tmp/centaur-api-server \
    && cp target/release/centaur-session-cli /tmp/centaur-session-cli

FROM debian:bookworm-slim

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /tmp/centaur-api-server /usr/local/bin/centaur-api-server
COPY --from=builder /tmp/centaur-session-cli /usr/local/bin/centaur-session-cli

# Runtime fragment files are read from SESSION_SANDBOX_IRON_PROXY_FRAGMENT_PATHS.
COPY services/iron-proxy /app/services/iron-proxy

ENTRYPOINT ["/usr/local/bin/centaur-api-server"]
