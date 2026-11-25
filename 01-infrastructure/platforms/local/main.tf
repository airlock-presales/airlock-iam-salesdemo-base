# Airlock IAM Salesdemo
# Phase: 1 - Infrastructure, platform: local
#
# The VM is created manually (e.g. VMware Workstation) and booted from the Talos ISO
# (see output iso_url). Nothing is created here, except the Talos image schematic.
#
# Output
# - contract outputs, see 01-infrastructure/README.md


module "config" {
    source = "../../../config"

    settings            = local.settings
    basedir             = var.basedir
}

locals {
    p = var.platform_local
}

module "talos-image" {
    source = "../../modules/talos-image"

    talos_version       = module.config.settings.vm.talos_version
    platform            = "metal"
}
