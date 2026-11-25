# Build & push the debug container (amd64 + arm64) to ghcr.io
# Prerequisites: docker with buildx, login with a PAT having write:packages:
#   echo <PAT> | docker login ghcr.io -u <github user> --password-stdin
# After the first push, set the package visibility to public (GitHub > Packages > argocd-cli > Settings).
# Update the image tag in applications/packages/argocd/argocd-cli/deployment.yaml accordingly.

REGISTRY=ghcr.io/airlock-presales/argocd-cli
VERSION=$(shell awk -F '=' '/ARG ARGO_VERSION/{print $$2}' Dockerfile)
BUILD_VERSION=1
PLATFORMS=linux/amd64#,linux/arm64

TS=$(shell date "+%Y/%m/%d %H:%M:%S")

all:
	@echo "info             Show container tag"
	@echo "build            Build container image for local platform (version: $(VERSION)-$(BUILD_VERSION))"
	@echo "push             Build for $(PLATFORMS) and push to $(REGISTRY)"

info:
	@echo "Tag: $(REGISTRY):$(VERSION)-$(BUILD_VERSION)"

build:
	docker buildx build . --load --build-arg BUILD_DATE="$(TS)" -t "$(REGISTRY):$(VERSION)-$(BUILD_VERSION)"

push:
	docker buildx build . --push --platform $(PLATFORMS) --build-arg BUILD_DATE="$(TS)" -t "$(REGISTRY):$(VERSION)-$(BUILD_VERSION)"
