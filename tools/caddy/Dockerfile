# Official Caddy pinned independently; no DNS modules or application credentials in this image.
FROM caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
RUN apk upgrade --no-cache \
    && addgroup -g 10001 otm && adduser -D -H -u 10001 -G otm -s /sbin/nologin otm \
    && mkdir -p /data /config && chown -R 10001:10001 /data /config
USER 10001:10001
EXPOSE 8080 8443 9090
CMD ["caddy", "run", "--config", "/etc/otm-caddy/Caddyfile", "--adapter", "caddyfile"]
