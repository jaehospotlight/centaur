FROM ironsh/iron-proxy:0.30.0@sha256:9a96eb935d22f8096574e95c2f510076ab4970440f65fb37d08b1f1767a08d45

USER root
RUN apk add --no-cache curl jq

COPY services/iron-proxy/iron-proxy.yaml /usr/local/share/iron-proxy/proxy.yaml.default
COPY --chmod=755 services/iron-proxy/entrypoint.sh /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
