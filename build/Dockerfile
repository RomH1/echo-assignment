# syntax=docker/dockerfile:1
#
# Builds the nginx .deb from upstream source on a clean debian:bookworm-slim
# base. No pre-baked binaries: we fetch nginx.org's own source package (the
# exact same source + Debian packaging that nginx.org uses to build the
# `nginx:1.25-bookworm` Docker Hub image), apply our two remediation
# patches, and run dpkg-buildpackage.
#
# Remediation techniques applied here:
#   1. Version bump  (CVE-2026-31789): libssl3/openssl are upgraded to a
#      Debian bookworm-security build that already contains the OpenSSL fix,
#      so the nginx we build links against (and the final image ships) a
#      patched OpenSSL instead of the 3.0.11-1~deb12u2 the original image
#      shipped.
#   2. Backport patch (CVE-2026-42533): patches/CVE-2026-42533.patch,
#      installed as a debian/patches quilt patch and applied automatically
#      by dpkg-source before the build.
#
# Output: /out/nginx_1.25.5-1~bookworm_<arch>.deb (use `--output` / the
# Makefile to extract it; see ../Makefile).

FROM debian:bookworm-slim AS builder

ARG NGINX_VERSION=1.25.5
ARG PKG_RELEASE=1~bookworm
ARG NGINX_ORIG_SHA256=2fe2294f8af4144e7e842eaea884182a84ee7970e11046ba98194400902bbec0
ARG NGINX_DEBIAN_SHA256=ed378f87b346f5a56a97d1a8313375bc00e8aa1e4da8a57eb9bca3d5268b5ffb

# --- base build tooling -----------------------------------------------
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        debhelper \
        devscripts \
        dpkg-dev \
        quilt \
        lsb-release \
        ca-certificates \
        curl \
      && rm -rf /var/lib/apt/lists/*

# --- CVE-2026-31789: version bump of the OpenSSL system library -------
# Pull the currently-published bookworm-security build of openssl/libssl3
# (already contains the upstream OCTET STRING heap-overflow fix) *before*
# we resolve nginx's own build-deps, so both the build headers and the
# resulting binary package link against the patched library.
RUN apt-get update \
      && apt-get install --no-install-recommends -y openssl libssl3 libssl-dev \
      && rm -rf /var/lib/apt/lists/* \
      && installed="$(dpkg-query -W -f='${Version}' libssl3)" \
      && echo "libssl3 installed: $installed" \
      && dpkg --compare-versions "$installed" ge "3.0.19-1~deb12u2" \
         || (echo "ERROR: libssl3 $installed is older than the fixed 3.0.19-1~deb12u2, CVE-2026-31789 not remediated" >&2; exit 1)

WORKDIR /build

# --- fetch upstream source: nginx.org's own Debian source package -----
# This is the identical source + packaging nginx.org uses to build the
# official nginx:1.25-bookworm image (verified against the .dsc checksums).
RUN curl -fsSLO "https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/nginx_${NGINX_VERSION}.orig.tar.gz" \
      && curl -fsSLO "https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/nginx_${NGINX_VERSION}-${PKG_RELEASE}.debian.tar.xz" \
      && echo "${NGINX_ORIG_SHA256}  nginx_${NGINX_VERSION}.orig.tar.gz" | sha256sum -c - \
      && echo "${NGINX_DEBIAN_SHA256}  nginx_${NGINX_VERSION}-${PKG_RELEASE}.debian.tar.xz" | sha256sum -c -

RUN tar xzf nginx_${NGINX_VERSION}.orig.tar.gz \
      && tar xJf nginx_${NGINX_VERSION}-${PKG_RELEASE}.debian.tar.xz -C nginx-${NGINX_VERSION}

# --- apply our patches: version bump is handled via apt above; the
# --- backport patch is dropped into debian/patches as a quilt patch ---
COPY patches/CVE-2026-42533.patch /build/nginx-${NGINX_VERSION}/debian/patches/CVE-2026-42533.patch
RUN mkdir -p /build/nginx-${NGINX_VERSION}/debian/patches \
      && echo "CVE-2026-42533.patch" >> /build/nginx-${NGINX_VERSION}/debian/patches/series

# --- build-deps declared by nginx's own debian/control -----------------
WORKDIR /build/nginx-${NGINX_VERSION}
RUN apt-get update \
      && apt-get build-dep --no-install-recommends -y . \
      && rm -rf /var/lib/apt/lists/*

# --- build the .deb -----------------------------------------------------
# dpkg-buildpackage runs "dpkg-source --before-build" first, which applies
# every patch listed in debian/patches/series (via quilt) before compiling.
RUN DEB_BUILD_OPTIONS="nocheck parallel=$(nproc)" \
      dpkg-buildpackage -b -uc -us

RUN mkdir -p /out \
      && cp /build/*.deb /out/ \
      && ls -la /out

FROM scratch AS export
COPY --from=builder /out/ /
