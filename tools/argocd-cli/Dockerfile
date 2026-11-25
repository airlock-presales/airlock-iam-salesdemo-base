ARG K8S_VERSION=1.35.9
ARG ARGO_VERSION=3.6.2
ARG KUBECOLOR_VERSION=0.8.0
ARG K9S_VERSION=0.51.0

FROM quay.io/argoproj/argocd:v${ARGO_VERSION} AS builder

FROM alpine:3.24
ARG K8S_VERSION
ARG ARGO_VERSION
ARG KUBECOLOR_VERSION
ARG K9S_VERSION
ARG BUILD_DATE
ARG TARGETARCH

LABEL org.opencontainers.image.source="https://github.com/airlock-presales/airlock-iam-demo-base-wip"
LABEL org.opencontainers.image.description="Airlock IAM Salesdemo debug container: argocd, kubectl, kubecolor, k9s"
LABEL build_info="Versions: K8S: ${K8S_VERSION} Argo: ${ARGO_VERSION} k9s: ${K9S_VERSION} Build-date: ${BUILD_DATE}"

# Install ArgoCD CLI
COPY --from=builder /usr/local/bin/argocd /usr/local/bin/argocd

# Install kubectl, kubecolor & k9s
RUN apk add --no-cache curl ca-certificates bash tzdata \
 && curl -fsSL https://dl.k8s.io/release/v${K8S_VERSION}/bin/linux/${TARGETARCH}/kubectl -o /usr/local/bin/kubectl \
 && curl -fsSL https://github.com/kubecolor/kubecolor/releases/download/v${KUBECOLOR_VERSION}/kubecolor_${KUBECOLOR_VERSION}_linux_${TARGETARCH}.tar.gz | tar xzf - -C /usr/local/bin kubecolor \
 && curl -fsSL https://github.com/derailed/k9s/releases/download/v${K9S_VERSION}/k9s_Linux_${TARGETARCH}.tar.gz | tar xzf - -C /usr/local/bin k9s \
 && chmod +x /usr/local/bin/*

USER 1000
ENV HOME=/var/tmp
WORKDIR /var/tmp

CMD ["/bin/sh", "-c", "while true; do sleep 3600; done"]
