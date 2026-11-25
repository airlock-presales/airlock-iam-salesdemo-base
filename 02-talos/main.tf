# Airlock IAM Salesdemo
# Phase: 2 - Talos
#
# Task
# - Configure Talos with config patch
# - Setup 2nd disk for Kubernetes local-path-provisioner
# - Bootstrap system (install as per config)
#
# Output
# - config to access Talos & Kubernetes


module "config" {
    source = "../config"

    settings            = local.settings
    basedir             = var.basedir
}

module "bootstrap" {
    source = "./bootstrap"

    settings            = module.config.settings
}
