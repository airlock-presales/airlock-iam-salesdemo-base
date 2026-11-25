# Airlock IAM Salesdemo - how it works

-This repository is used like a library by the instance repositories. The documentation for setting up and using an instance (workstation, platforms, settings, usage, backup and restore) is in the [instance template](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template) - start there. This page describes how the installation works internally. What can be demonstrated: [use cases](use-cases.md). Overview of the components with diagrams, for integrators: [architecture](architecture.md).

# Architecture

A single virtual machine runs Talos Linux with a single-node Kubernetes cluster. Everything on it is deployed by ArgoCD from this repository.

| Component | Purpose | URL |
|-----------|---------|-----|
| Airlock Microgateway | Gateway API implementation, ingress with security policies | |
| Airlock IAM | Loginapp and Adminapp | `https://<fqdn>/auth-login/`, `https://<fqdn>/auth-admin/` |
| MariaDB (operator) | IAM database | |
| Valkey | Microgateway session store | |
| cert-manager | internal CA, optionally Let's Encrypt | |
| PureLB | IP address for the gateway (Service type LoadBalancer) | |
| local-path-provisioner | persistent volumes on the data disk | |
| ArgoCD | deploys and maintains everything | `https://<fqdn>/argocd/` |
| Adminer | database UI | `https://<fqdn>/adminer/` |
| Headlamp | Kubernetes UI | `https://<fqdn>/headlamp/` |
| Mailpit | catches emails sent by IAM (if no SMTP server is set) | `https://<fqdn>/mailpit/` |
| qr-service | QR codes for the identity proofing (PXL Vision) | `https://<fqdn>/qr/qrcode?txt=...` |
| argocd-cli | debug container: argocd, kubectl, k9s | `kubectl exec` |

## Installation phases

The instance repository's `Makefile` runs `bin/tofuwrap` for each phase. Each phase is an OpenTofu root project; the state is stored encrypted in the instance repository. The provider lock files (`.terraform.lock.hcl`) belong to the instance too: tofu keeps them in the root project directory of the base checkout, `tofuwrap` copies them from the instance's `locks/` before each run and back afterwards (never committed in this repository).

| Phase | Directory | Creates |
|-------|-----------|---------|
| 1 | `01-infrastructure/platforms/<platform>` | VM and its environment; see [contract](../01-infrastructure/README.md) |
| 2 | `02-talos` | Talos configuration, Kubernetes bootstrap; writes `output/kubeconfig.yaml`, `output/talosconfig.yaml` |
| 3 | `03-argocd` | settings, licenses and secrets, ArgoCD, app-of-apps - ArgoCD deploys the rest |

## Repository structure

```
salesdemo/
├── bin/tofuwrap             ← wrapper around tofu, run from the instance directory
├── bin/iamdb, bin/iamconfig ← IAM database backup/restore, IAM configuration (make targets)
├── iam/iam-config.yaml      ← IAM configuration template, copied to the instance by 'make init'
├── 01-infrastructure/       ← phase 1: one root project per platform (platforms/), shared modules
├── 02-talos/                ← phase 2
├── 03-argocd/               ← phase 3
├── config/                  ← settings structure, validation, release-fixed values
│   └── root/vars_config.tf  ← instance settings, copied into all root projects ('make settings')
├── data/templates/          ← templates for generated files
├── applications/
│   ├── argocd/bootstrap/    ← ArgoCD applications (app-of-apps)
│   └── packages/            ← manifests of each application (kustomize, helm via kustomize)
├── tools/argocd-cli/        ← debug container image
├── tools/qr-service/        ← QR code service image (Go)
└── docs/
```

Per-instance values reach the Kubernetes manifests through the ConfigMap `argocd/project-settings`: the `apply-config.sh` script of an application replaces `@@...@@` placeholders before rendering (ArgoCD lovely plugin). ArgoCD caches rendered manifests per git revision and application: the hash of the project settings (plugin env `SETTINGS_HASH`, set by OpenTofu in the app-of-apps and passed on to all applications) makes ArgoCD render them again when a setting changes. The configmap is mounted into the repo server and updated with a delay: every `apply-config.sh` waits (max. 60 s) until the mounted settings match the hash, otherwise it fails instead of rendering old values. The IAM configuration comes from the instance repository (`iam/`), see [usage](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template/blob/main/docs/usage.md#iam-configuration).
