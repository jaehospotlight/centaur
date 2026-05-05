FROM ironsh/iron-proxy:0.21.0@sha256:2baee4f9f920277b8d8240381227f41532c384cb56326993a4ddacf1486bb978

USER root
RUN apk add --no-cache curl jq

COPY services/iron-proxy/iron-proxy.yaml /usr/local/share/iron-proxy/proxy.yaml.default
COPY --chmod=755 services/iron-proxy/entrypoint.sh /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
