# syntax=docker/dockerfile:1.7

FROM ironsh/iron-proxy:0.46.0@sha256:2561948695928b0fa4b78835ae2b437c9915f209a59442a5807a86c0d70e950d

USER root
RUN --mount=type=cache,target=/var/cache/apk,sharing=locked \
    apk add --update-cache --cache-dir /var/cache/apk curl jq

COPY services/iron-proxy/iron-proxy.yaml /usr/local/share/iron-proxy/proxy.yaml.default
COPY --chmod=755 services/iron-proxy/entrypoint.sh /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
