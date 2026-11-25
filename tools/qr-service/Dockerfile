# qr-service - QR code (PNG) over HTTP, see main.go
ARG GO_VERSION=1.24

FROM --platform=$BUILDPLATFORM golang:${GO_VERSION}-alpine AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags="-s -w" -o /qr-service .

FROM gcr.io/distroless/static-debian12:nonroot
ARG BUILD_DATE
LABEL org.opencontainers.image.source="https://github.com/airlock-presales/airlock-iam-demo-base-wip" \
      org.opencontainers.image.description="QR code (PNG) over HTTP for the Airlock IAM salesdemo" \
      org.opencontainers.image.created="${BUILD_DATE}"
COPY --from=build /qr-service /qr-service
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/qr-service"]
