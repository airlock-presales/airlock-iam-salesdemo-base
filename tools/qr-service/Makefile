# Build & push the QR code service (amd64 + arm64) to ghcr.io
# Prerequisites: docker with buildx, login with a PAT having write:packages:
#   echo <PAT> | docker login ghcr.io -u <github user> --password-stdin
# After the first push, set the package visibility to public (GitHub > Packages > qr-service > Settings).
# Update the image tag in applications/packages/qr-service/qr-service.yaml accordingly.

REGISTRY=ghcr.io/airlock-presales/qr-service
VERSION=1.0.0
PLATFORMS=linux/amd64#linux/arm64

TS=$(shell date "+%Y/%m/%d %H:%M:%S")

all:
	@echo "info             Show container tag"
	@echo "test             Run locally on port 8080 (go run)"
	@echo "build            Build container image for local platform (version: $(VERSION))"
	@echo "push             Build for $(PLATFORMS) and push to $(REGISTRY)"

info:
	@echo "Tag: $(REGISTRY):$(VERSION)"

test:
	go run .

build:
	docker buildx build . --load --build-arg BUILD_DATE="$(TS)" -t "$(REGISTRY):$(VERSION)"

push:
	docker buildx build . --push --platform $(PLATFORMS) --build-arg BUILD_DATE="$(TS)" -t "$(REGISTRY):$(VERSION)"
