# Task
# - Register Talos image schematic (system extensions) with the Talos Image Factory
# - Provide platform-specific image URLs and installer image
#
# Output
# - disk image / ISO URL, installer image

terraform {
  required_providers {
    talos = {
      source  = "siderolabs/talos"
      version = "0.12.0"
    }
  }
}

variable "talos_version" {
  type        = string
  description = "Talos version, without leading 'v'"
}

variable "platform" {
  type        = string
  description = "Talos platform of the image, e.g. metal, azure, aws, gcp"
}

variable "extensions" {
  type        = list(string)
  description = "Official system extensions, e.g. siderolabs/qemu-guest-agent"
  default     = []
}

resource "talos_image_factory_schematic" "this" {
  schematic = yamlencode({
    customization = {
      systemExtensions = {
        officialExtensions = var.extensions
      }
    }
  })
}

data "talos_image_factory_urls" "this" {
  talos_version = "v${var.talos_version}"
  schematic_id  = talos_image_factory_schematic.this.id
  platform      = var.platform
}

output "schematic_id" {
  value = talos_image_factory_schematic.this.id
}

output "disk_image_url" {
  value = data.talos_image_factory_urls.this.urls.disk_image
}

output "iso_url" {
  value = data.talos_image_factory_urls.this.urls.iso
}

output "installer_image" {
  value = data.talos_image_factory_urls.this.urls.installer
}
