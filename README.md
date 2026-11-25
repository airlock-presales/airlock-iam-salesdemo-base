# Airlock IAM Salesdemo

Automated, reproducible setup of an Airlock IAM demo environment: a single-node Kubernetes cluster based on Talos, set up by OpenTofu, with all services deployed by ArgoCD.

This repository contains the generic project. Each demo instance has its own, separate instance repository, created from the [instance template](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template):
- `variables.auto.tfvars` - instance settings, encrypted with sops/age (all keys: `variables.template` of the instance template)
- `release` - release (git tag or branch) of this repository to deploy
- `Makefile` - targets to initialise, build and remove the instance, backup/restore, IAM configuration
- `iam/` - IAM configuration and server-side texts, created from [iam/](iam/) of this repository by `make init`
- `state/` - OpenTofu state, encrypted with the instance's `sec_state_passphrase`

## Documentation

- Setting up and using an instance (workstation, platforms, settings, usage, backup and restore): [instance template](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template) - the entry point for partners.
- How the installation works (architecture, phases, repository structure): [docs](docs/README.md).

## Quick start

In an instance repository (see [docs/instance.md](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template/blob/main/docs/instance.md) of the instance template):
```
export SOPS_AGE_KEY_FILE="${PWD}/age.keys"
make init      # checks out this repository at the instance's release, initialises OpenTofu, creates iam/
make build     # creates VM, Talos, ArgoCD and deploys the salesdemo
```
