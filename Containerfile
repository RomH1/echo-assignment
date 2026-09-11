# syntax=docker/dockerfile:1
#
# Final image: install the .deb produced by build/Dockerfile into a
# minimal debian:bookworm-slim base. This is meant to be a drop-in
# replacement for nginx:1.25-bookworm, so filesystem layout, user, ports
# and entrypoint mirror that image exactly (verified against its published
# manifest/config, see README.md).
#
# Build with `make image` (which runs `make build-deb` first), or directly:
#   docker buildx build --output type=local,dest=dist build/ -f build/Dockerfile --target export
#   docker build -t echo-nginx:1.25-bookworm-patched .

FROM debian:bookworm-slim

LABEL maintainer="Echo assignment"

# nginx.org's own package pulls these in as runtime deps; installing them
# explicitly keeps the apt-get invocation order predictable and lets us
# assert the OpenSSL version bump (CVE-2026-31789) below.
ARG NGINX_DEB=dist/nginx_1.25.5-1~bookworm_amd64.deb

# create nginx user/group first, to be consistent with the upstream image
RUN groupadd --system --gid 101 nginx \
    && useradd --system --gid nginx --no-create-home --home /nonexistent \
       --comment "nginx user" --shell /bin/false --uid 101 nginx

COPY ${NGINX_DEB} /tmp/nginx.deb

# --- install our patched nginx .deb, plus the OpenSSL version bump ------
# CVE-2026-31789: openssl/libssl3 are upgraded to a fixed bookworm-security
# build here too (belt-and-braces with the build stage: this is the copy
# that actually ships at runtime).
RUN apt-get update \
    && apt-get install --no-install-recommends -y openssl libssl3 gettext-base curl ca-certificates \
    && installed="$(dpkg-query -W -f='${Version}' libssl3)" \
    && dpkg --compare-versions "$installed" ge "3.0.19-1~deb12u2" \
       || (echo "ERROR: libssl3 $installed is older than the fixed 3.0.19-1~deb12u2" >&2; exit 1) \
    && apt-get install --no-install-recommends -y /tmp/nginx.deb \
    && rm -f /tmp/nginx.deb \
    && apt-get purge -y --auto-remove \
    && rm -rf /var/lib/apt/lists/* \
    # forward request and error logs to docker log collector, same as upstream
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && mkdir /docker-entrypoint.d

COPY docker-entrypoint/docker-entrypoint.sh /
COPY docker-entrypoint/10-listen-on-ipv6-by-default.sh /docker-entrypoint.d
COPY docker-entrypoint/15-local-resolvers.envsh /docker-entrypoint.d
COPY docker-entrypoint/20-envsubst-on-templates.sh /docker-entrypoint.d
COPY docker-entrypoint/30-tune-worker-processes.sh /docker-entrypoint.d

ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 80

STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]
