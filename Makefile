GENERIC_ARCH := $(shell dpkg --print-architecture 2>/dev/null || echo amd64)
NGINX_VERSION := 1.25.5
PKG_RELEASE   := 1~bookworm
DEB_NAME      := nginx_$(NGINX_VERSION)-$(PKG_RELEASE)_$(GENERIC_ARCH).deb
IMAGE_TAG     := echo-nginx:1.25-bookworm-patched

.PHONY: all build-deb image test clean

all: image

## Stage 1: compile nginx from source on a clean debian:bookworm-slim
## builder and export the resulting .deb to dist/.
build-deb:
	docker buildx build \
		--file build/Dockerfile \
		--target export \
		--output type=local,dest=dist \
		build
	@ls -la dist/*.deb

## Stage 2: install the .deb produced above into a minimal Debian base,
## matching the upstream nginx:1.25-bookworm image layout exactly.
image: build-deb
	docker build \
		--build-arg NGINX_DEB=dist/$(DEB_NAME) \
		-f Containerfile \
		-t $(IMAGE_TAG) \
		.
	@echo "Built $(IMAGE_TAG)"
	@docker image inspect $(IMAGE_TAG) --format 'Size: {{.Size}} bytes'

test:
	@echo "test/ not implemented yet (see README.md Residual risk)" >&2
	@exit 1

clean:
	rm -rf dist
