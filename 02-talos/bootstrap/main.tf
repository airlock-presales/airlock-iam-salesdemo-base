# Task
# - Configure Talos with config patch
# - Setup 2nd disk for Kubernetes local-path-provisioner
# - Bootstrap system (install as per config)
# - Wait until Kubernetes cluster is ready
#
# Output
# - config to access Talos & Kubernetes


data "terraform_remote_state" "infrastructure" {
  backend = "local"

  config = {
    path = "${var.settings.paths.state}/01-infrastructure.tfstate"
  }
}

locals {
  # phase 1 contract, see 01-infrastructure/README.md
  infra               = data.terraform_remote_state.infrastructure.outputs
  # endpoint_ip: Talos/Kubernetes API from the workstation (tofu, talosctl, kubectl); node_ip: the address on
  # the node's interface (kubelet, etcd, cluster endpoint) - different where the platform NATs the public IP
  # (Azure); node_ip falls back to endpoint_ip for a phase 1 state from before the output existed.
  # Talos API calls: endpoint = endpoint_ip (connection), node = node_ip (target) - with the public IP as
  # target, a configured node forwards the call to it, through Azure's NAT and the NSG. A node in maintenance
  # mode gets its first configuration from talosctl (terraform_data.initial_config)
  endpoint_ip         = local.infra.endpoint_ip
  node_ip             = try(local.infra.node_ip, local.infra.endpoint_ip)
  # kubeconfig for the workstation: server = endpoint_ip (the generated one points to the cluster endpoint)
  kubeconfig_raw      = replace(talos_cluster_kubeconfig.kubeconfig.kubeconfig_raw, "https://${local.node_ip}:6443", "https://${local.endpoint_ip}:6443")
  # null: the VM boots from a Talos disk image (cloud platforms) - no install, it would wipe the disk
  # Talos runs from, including the configuration just applied (node back in maintenance mode)
  # (a null output is not stored in the phase 1 state: try)
  disk_dev            = try(local.infra.system_disk_dev, null)

  install = local.disk_dev == null ? null : yamlencode({
    apiVersion = "v1alpha1"
    kind = "UnattendedInstallConfig"
    installer = {
      image = local.infra.installer_image
    }
    provisioning = {
      diskSelector = {
        match = "disk.dev_path == \"${coalesce(local.disk_dev, "-")}\""
      }
      wipe = true
    }
  })
  userdata = yamlencode({
    apiVersion = "v1alpha1"
    kind = "UserVolumeConfig"
    name: "local-path-provisioner"
    volumeType = "partition"
    provisioning = {
      diskSelector = {
        match = "! system_disk"
      }
      maxSize = "${var.settings.vm.disk_size_data}GB"
    }
    filesystem = {
      type = "xfs"
    }
  })
  # Talos API certificate: v1alpha1 machine.certSANs
  certsans = yamlencode({
    machine = {
      certSANs = local.infra.cert_sans
    }
  })
  # node IP for kubelet and etcd: PureLB (local mode) adds the LoadBalancer addresses to the node's
  # interface - without explicit subnets, Talos could pick one of them as node IP.
  # Kubelet: since Talos 1.14 in the document KubeNodeConfig (.machine.kubelet conflicts);
  # etcd: still in the v1alpha1 document.
  nodeip = yamlencode({
    apiVersion = "v1alpha1"
    kind = "KubeNodeConfig"
    nodeIP = {
      validSubnets = ["${local.node_ip}/32"]
    }
  })
  etcdip = yamlencode({
    cluster = {
      etcd = {
        advertisedSubnets = ["${local.node_ip}/32"]
      }
    }
  })
  # Kubernetes API certificate: since Talos 1.14 a separate document (.cluster.apiServer conflicts)
  apiserver = yamlencode({
    apiVersion = "v1alpha1"
    kind = "KubeAPIServerConfig"
    certExtraSANs = local.infra.cert_sans
  })
  timesync = yamlencode({
    apiVersion = "v1alpha1"
    kind = "TimeSyncConfig"
    ntp = {
      servers: var.settings.vm.ntp_servers
    }
  })
}

resource "talos_machine_secrets" "salesdemo" {
  talos_version        = var.settings.vm.talos_version
}

data "talos_machine_configuration" "salesdemo" {
  cluster_name         = var.settings.demo.name
  cluster_endpoint     = "https://${local.node_ip}:6443"
  machine_type         = "controlplane"
  machine_secrets      = talos_machine_secrets.salesdemo.machine_secrets
  talos_version        = var.settings.vm.talos_version
  kubernetes_version   = "v${var.settings.kubernetes.version}"
  # patches applied here (provider libraries of the Talos version in use): the finished configuration
  # goes to talosctl (initial_config), which then does not need to know newer documents (KubeNodeConfig
  # is Talos 1.14 - talosctl 1.13 could not decode it), and to the provider's apply
  config_patches       = local.config_patches
}

locals {
  # Single node: workloads must run on the control plane. Removing the taint from the
  # generated config is the only approach that worked reliably (allowSchedulingOnControlPlanes,
  # KubeNodeConfig patches etc. did not).
  machine_config = replace(
    data.talos_machine_configuration.salesdemo.machine_configuration,
    "node-role.kubernetes.io/control-plane: NoSchedule",
    ""
  )
  config_patches = [for p in [local.install, local.certsans, local.etcdip, local.nodeip, local.apiserver, local.userdata, local.timesync] : p if p != null]
}

# First configuration of a node in maintenance mode: talosctl apply-config --insecure (the documented
# procedure). The provider's apply did not get through on Azure: it sends the first, unauthenticated
# request with node metadata, which was rejected, then fell back to the cluster CA ("certificate signed
# by unknown authority" until the timeout). Skipped if the node is not in maintenance mode (configured).
# The configuration (secrets) is passed via environment and written to a temporary file (mode 600).
resource "terraform_data" "initial_config" {
  triggers_replace = [local.endpoint_ip, talos_machine_secrets.salesdemo.id]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      TALOS_ENDPOINT    = local.endpoint_ip
      TALOS_CONFIG      = local.machine_config
    }
    command = <<-EOT
      set -euo pipefail
      command -v talosctl >/dev/null || { echo "talosctl not found (required, see docs/workstation.md)" >&2; exit 1; }
      if ! talosctl version --insecure --nodes "$TALOS_ENDPOINT" >/dev/null 2>&1; then
        echo "Node $TALOS_ENDPOINT not in maintenance mode - configuration applied by the provider"
        exit 0
      fi
      dir="$(mktemp -d)"
      trap 'rm -rf "$dir"' EXIT
      chmod 700 "$dir"
      umask 077
      printf '%s\n' "$TALOS_CONFIG" > "$dir/config.yaml"
      echo "Applying the first configuration to $TALOS_ENDPOINT (maintenance mode) ..."
      talosctl apply-config --insecure --nodes "$TALOS_ENDPOINT" --file "$dir/config.yaml"
    EOT
  }
}

# Configuration (updates later on): the node is configured by now, authenticated with the cluster CA;
# endpoint = public IP, node = node IP (see locals)
resource "talos_machine_configuration_apply" "salesdemo_apply" {
  depends_on                  = [terraform_data.initial_config]
  client_configuration        = talos_machine_secrets.salesdemo.client_configuration
  apply_mode                  = "auto"
  node                        = local.node_ip
  endpoint                    = local.endpoint_ip

  # finished configuration (patches applied in data.talos_machine_configuration)
  machine_configuration_input = local.machine_config

  timeouts = {
    create = "15m"
    update = "15m"
  }
}

resource "talos_machine_bootstrap" "bootstrap" {
  depends_on           = [talos_machine_configuration_apply.salesdemo_apply]
  client_configuration = talos_machine_secrets.salesdemo.client_configuration
  node                 = local.node_ip
  endpoint             = local.endpoint_ip
}

resource "talos_cluster_kubeconfig" "kubeconfig" {
  depends_on           = [talos_machine_bootstrap.bootstrap]
  client_configuration = talos_machine_secrets.salesdemo.client_configuration
  node                 = local.node_ip
  endpoint             = local.endpoint_ip
}

data "talos_client_configuration" "client_config" {
  cluster_name         = var.settings.demo.name
  client_configuration = talos_machine_secrets.salesdemo.client_configuration
  endpoints            = [local.endpoint_ip]
  nodes                = [local.node_ip]
}

resource "local_file" "env-setup" {
    filename             = "${var.settings.paths.output}/env-setup"
    content              = templatefile( "${var.settings.paths.templates}/env-setup.tftpl", { dir=var.settings.paths.output } )
    file_permission      = 0600
}

resource "local_file" "talosconfig" {
    filename             = "${var.settings.paths.output}/talosconfig.yaml"
    content              = templatefile( "${var.settings.paths.templates}/yaml.tftpl", { data=data.talos_client_configuration.client_config.talos_config } )
    file_permission      = 0600
}

resource "local_file" "kubeconfig" {
    filename             = "${var.settings.paths.output}/kubeconfig.yaml"
    content              = templatefile( "${var.settings.paths.templates}/yaml.tftpl", { data=local.kubeconfig_raw } )
    file_permission      = 0600
}

data "talos_cluster_health" "salesdemo" {
  depends_on           = [talos_machine_bootstrap.bootstrap]
  client_configuration = talos_machine_secrets.salesdemo.client_configuration
  control_plane_nodes  = [local.node_ip]
  endpoints            = [local.endpoint_ip]
  # the Kubernetes checks call the API at the cluster endpoint (node_ip), unreachable from the workstation
  # where the platform NATs the public IP (Azure) - only the Talos checks there (etcd, apid, kubelet, boot)
  skip_kubernetes_checks = local.node_ip != local.endpoint_ip
}

# Kubernetes API reachable from the workstation (phase 3 uses it right away): without the Kubernetes
# checks above (Azure), phase 2 could end while the API server is still starting ("connection refused"
# in phase 3). /readyz is allowed anonymously; -k: readiness only, no data exchanged.
resource "terraform_data" "kubernetes_api_ready" {
  depends_on       = [data.talos_cluster_health.salesdemo]
  triggers_replace = [talos_machine_bootstrap.bootstrap.id]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      url="https://${local.endpoint_ip}:6443/readyz"
      echo "Waiting for the Kubernetes API ($url, max. 10 minutes) ..."
      for _ in $(seq 120); do
        [[ "$(curl -ks -o /dev/null -w '%%{http_code}' --max-time 5 "$url")" == "200" ]] && { echo "Kubernetes API ready"; exit 0; }
        sleep 5
      done
      echo "Kubernetes API not ready after 10 minutes: $url" >&2
      exit 1
    EOT
  }
}
