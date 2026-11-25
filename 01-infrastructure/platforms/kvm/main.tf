# Airlock IAM Salesdemo
# Phase: 1 - Infrastructure, platform: kvm
#
# Task
# - Download and unpack Talos raw image (with qemu guest agent)
# - Allocate disks in pool, system disk initialised with the Talos image
# - Create VM with system & data disk and network interface
#
# Output
# - contract outputs, see 01-infrastructure/README.md


module "config" {
    source = "../../../config"

    settings            = local.settings
    basedir             = var.basedir
}

module "talos-image" {
    source = "../../modules/talos-image"

    talos_version       = module.config.settings.vm.talos_version
    platform            = "metal"
    extensions          = ["siderolabs/qemu-guest-agent"]
}

locals {
    p        = var.platform_kvm
    name     = module.config.settings.demo.name

    # VM size (settings platform_kvm.vcpu/memory)
    vcpu     = local.p.vcpu
    memory   = local.p.memory  # GiB

    files    = "${var.basedir}/.tofu/files"
    talos_raw = "${local.files}/talos-${module.config.settings.vm.talos_version}-${module.talos-image.schematic_id}.raw"
}

resource "terraform_data" "talos_raw" {
  triggers_replace = [
    module.talos-image.disk_image_url,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/sh", "-c"]
    command     = <<-EOT
      set -eu
      mkdir -p "${local.files}"
      curl -fsSL "${module.talos-image.disk_image_url}" | unzstd -f -o "${local.talos_raw}"
    EOT
  }
}

resource "libvirt_volume" "system" {
  name          = "${local.name}-system"
  pool          = local.p.pool
  # in bytes: the provider compares the capacity with the size of the uploaded image without
  # applying capacity_unit (40 GiB taken as 40 bytes: "volume capacity 40 is smaller than upload content length")
  capacity      = module.config.settings.vm.disk_size_system * 1024 * 1024 * 1024
  create = {
    content = {
      url = local.talos_raw
    }
  }
  target = {
    format = {
      type = "raw"
    }
  }

  depends_on = [terraform_data.talos_raw]
}

resource "libvirt_volume" "data" {
  name          = "${local.name}-data"
  pool          = local.p.pool
  # in bytes, like the system volume
  capacity      = module.config.settings.vm.disk_size_data * 1024 * 1024 * 1024
}

# DHCP reservation ip for mac in the libvirt-managed network (platform_kvm.dhcp_reservation, default):
# created before the VM, removed when it is destroyed. Same ssh access as the libvirt provider.
# Bridged networks (dhcp_reservation = false): reservation in the network's DHCP server, manual.
resource "terraform_data" "dhcp_reservation" {
  count = local.p.dhcp_reservation ? 1 : 0

  triggers_replace = [local.p.host, local.p.network, local.p.mac, local.p.ip]
  input = {
    ssh     = "${local.p.user}@${local.p.host}"
    network = local.p.network
    mac     = local.p.mac
    entry   = "<host mac='${local.p.mac}' name='${local.name}' ip='${local.p.ip}'/>"
  }

  provisioner "local-exec" {
    interpreter = ["/bin/sh", "-c"]
    command     = <<-EOT
      set -eu
      # an existing reservation for this MAC (e.g. from an earlier run or set manually) is replaced
      ssh ${self.input.ssh} "virsh -c qemu:///system net-update ${self.input.network} delete ip-dhcp-host \"<host mac='${self.input.mac}'/>\" --live --config" >/dev/null 2>&1 || true
      ssh ${self.input.ssh} "virsh -c qemu:///system net-update ${self.input.network} add-last ip-dhcp-host \"${self.input.entry}\" --live --config"
    EOT
  }

  provisioner "local-exec" {
    when        = destroy
    on_failure  = continue
    interpreter = ["/bin/sh", "-c"]
    command     = <<-EOT
      ssh ${self.input.ssh} "virsh -c qemu:///system net-update ${self.input.network} delete ip-dhcp-host \"<host mac='${self.input.mac}'/>\" --live --config"
    EOT
  }
}

resource "libvirt_domain" "talos" {
  name        = local.name
  memory      = local.memory
  memory_unit = "GiB"
  vcpu        = local.vcpu
  running     = true
  type        = "kvm"

  # the reservation must exist before the VM requests its address
  depends_on = [terraform_data.dhcp_reservation]

  cpu = {
    mode = "host-passthrough"
  }

  os = {
    type         = "hvm"
    type_arch    = "x86_64"
    type_machine = "pc"
    boot_devices = [{dev = "hd"}]
  }

  devices = {
    disks = [
      {
        source = {
          volume = {
            volume = libvirt_volume.system.name
            pool   = local.p.pool
          }
        }
        target = {
          dev = "vda"
          bus = "virtio"
        }
      },
      {
        source = {
          volume = {
            volume = libvirt_volume.data.name
            pool   = local.p.pool
          }
        }
        target = {
          dev = "vdb"
          bus = "virtio"
        }
      },
    ]
    interfaces = [
      {
        type = "network"
        model = {
          type = "virtio"
        }
        mac = {
          address = local.p.mac
        }
        source = {
          network = {
            network = local.p.network
          }
        }
      }
    ]
    channels = [
      {
        protocol = { type = "unix" }
        target = {
          virt_io = { name = "org.qemu.guest_agent.0" }
        }
      },
      {
        protocol = { type = "spicevmc" }
        target = {
          virt_io = { name = "com.redhat.spice.0" }
        }
      },
    ]
    serials = [
      {
        protocol = { type = "pty" }
        target = {
          port = "0"
        }
      }
    ]
    console = [
      {
        protocol = { type = "pty" }
        target = {
          type = "serial"
          port = "0"
        }
      },
      {
        protocol = { type = "pty" }
        target = {
          type = "virtio"
          port = "0"
        }
      }
    ]
    graphics = [
      {
        spice = {
          auto_port = true
        }
      }
    ]
    videos = [
      {
        model = { type = "virtio" }
      }
    ]
  }
}
