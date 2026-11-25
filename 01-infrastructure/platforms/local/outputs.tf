# --- contract, see 01-infrastructure/README.md ---

output "endpoint_ip" {
    value = local.p.ip
}

output "node_ip" {
    value = local.p.ip
}

output "cert_sans" {
    value = [local.p.ip]
}

output "system_disk_dev" {
    value = local.p.disk
}

output "installer_image" {
    value = module.talos-image.installer_image
}

output "lb_pool" {
    value = local.p.lb_pool
}

output "lb_subnet" {
    value = local.p.lb_subnet
}

# --- platform-specific ---

output "iso_url" {
    description = "Talos ISO to boot the VM from"
    value       = module.talos-image.iso_url
}
