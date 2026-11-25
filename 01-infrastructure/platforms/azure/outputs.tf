# --- contract, see 01-infrastructure/README.md ---

output "endpoint_ip" {
    value = azurerm_public_ip.admin.ip_address
}

# the public IP is NATed by Azure, the node only has its private IP on the interface
output "node_ip" {
    value = azurerm_network_interface.this.private_ip_address
}

output "cert_sans" {
    value = [azurerm_public_ip.admin.ip_address]
}

# the VM boots from the Talos Azure disk image - nothing to install (an install would wipe that disk)
output "system_disk_dev" {
    value = null
}

output "installer_image" {
    value = module.talos-image.installer_image
}

output "lb_pool" {
    value = "${local.lb_ip}-${local.lb_ip}"
}

output "lb_subnet" {
    value = local.cidr_subnet
}

# --- platform-specific ---

# make stop / make start (bin/vmpower)
output "azure_resource_group" {
    value = local.rg_name
}

output "azure_vm_name" {
    value = azurerm_linux_virtual_machine.this.name
}

output "lb_public_fqdn" {
    description = "Azure DNS name of the demo public IP (setting dns_label) - demo_fqdn can be this name or a CNAME to it"
    value       = azurerm_public_ip.lb.fqdn
}

output "lb_public_ip" {
    description = "Public IP of the demo - demo_fqdn must resolve to it"
    value       = azurerm_public_ip.lb.ip_address
}
