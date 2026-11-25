# Phase 1 - Infrastructure

One OpenTofu root project per platform in `platforms/<platform>`, selected by the instance setting `platform`.
Each creates the virtual machine and everything around it, ready to receive its Talos configuration in phase 2.

## Adding a platform

1. Create `platforms/<name>/` - copy an existing platform as a start
2. Add a variable `platform_<name>` with the platform's settings to `config/root/vars_config.tf`,
   add `<name>` to the validation of variable `platform`, run `make settings`
3. Add the platform to `make settings` in `01-infrastructure/Makefile`
4. Document requirements and preparation in `docs/`

## Contract

Every platform root project must provide these outputs, consumed by phase 2 (Talos) and phase 3 (ArgoCD):

| Output            | Description |
|-------------------|-------------|
| `endpoint_ip`     | IP address to reach the Talos API (50000) and Kubernetes API (6443) from the workstation |
| `node_ip`         | IP address on the node's interface (kubelet, etcd, Kubernetes API inside the cluster); the same as `endpoint_ip` unless the platform NATs it (Azure: private IP of the NIC) |
| `cert_sans`       | additional IP addresses/names for the Talos and Kubernetes API certificates |
| `system_disk_dev` | device to install Talos to, e.g. /dev/sda (boot from ISO); `null` if the VM boots from a Talos disk image (cloud platforms) - no install, it would wipe the disk Talos runs from |
| `installer_image` | Talos installer image, from module `talos-image` |
| `lb_pool`         | IP range or single IP for LoadBalancer services (PureLB) |
| `lb_subnet`       | subnet of `lb_pool` |

The state is stored as `<instance>/state/01-infrastructure.tfstate`, regardless of the platform.
