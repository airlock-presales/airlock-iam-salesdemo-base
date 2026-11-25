# Airlock IAM Salesdemo
# Phase: 1 - Infrastructure, platform: azure
#
# Task
# - Resource group, network, NSG
# - Upload Talos VHD (Image Factory, platform azure) and create image
# - VM with system & data disk, one NIC with two IP configurations:
#   - primary:   admin public IP - Talos API (50000) & Kubernetes API (6443), restricted to admin IPs
#   - secondary: static private IP used as LoadBalancer pool (PureLB), with the public IP for
#                the demo (80/443) - demo_fqdn must resolve to it (output lb_public_ip);
#                port 8443 (Adminapp, local administrator) restricted to admin IPs
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
    platform            = "azure"
}

locals {
  p   = var.platform_azure
  cfg = module.config.settings

  # fixed infrastructure settings
  # setting platform_azure.resource_group, default salesdemo-<demo name>; with resource_group_existing
  # the group is only looked up (e.g. given by the subscription owner) and kept by 'make remove'
  resource_group = coalesce(local.p.resource_group, "salesdemo-${local.cfg.demo.name}")
  rg_existing    = local.p.resource_group_existing
  # DNS label of the demo public IP: setting dns_label, default airlock-<demo name> (max. 63 characters), "" for none
  dns_label      = local.p.dns_label != null ? local.p.dns_label : trimsuffix(substr("airlock-${local.cfg.demo.name}", 0, 63), "-")
  # the resources are created in the region of the setting 'location' (may differ from the group's)
  rg_name        = local.rg_existing ? data.azurerm_resource_group.existing[0].name : azurerm_resource_group.this[0].name
  vm_size        = local.p.vm_size     # setting platform_azure.vm_size, default Standard_D4s_v5 (no temporary disk)
  disk_type      = "Premium_LRS"
  cidr_vnet      = "10.40.0.0/16"
  cidr_subnet    = "10.40.1.0/24"
  lb_ip          = cidrhost(local.cidr_subnet, 100)
  # node IP: static - it is part of the Talos configuration (etcd, kubelet, cluster endpoint) and must
  # survive a deallocate/start (make stop/start); .4 is the first address Azure hands out in a subnet
  node_ip        = cidrhost(local.cidr_subnet, 4)

  tags = {
    managed-by = "opentofu"
    workload   = "airlock-iam-salesdemo"
    instance   = local.cfg.demo.name
  }

  talos_blob = "talos-${local.cfg.vm.talos_version}-${module.talos-image.schematic_id}-azure-amd64.vhd"
}

resource "azurerm_resource_group" "this" {
  count    = local.rg_existing ? 0 : 1
  name     = local.resource_group
  location = local.p.location
  tags     = local.tags
}

# instances from before the setting resource_group_existing: the group keeps its state entry
moved {
  from = azurerm_resource_group.this
  to   = azurerm_resource_group.this[0]
}

data "azurerm_resource_group" "existing" {
  count = local.rg_existing ? 1 : 0
  name  = local.resource_group
}


# --- Talos image ---

# storage account names must be globally unique
resource "random_string" "storage" {
  length  = 12
  upper   = false
  special = false
}

resource "azurerm_storage_account" "this" {
  name                     = "salesdemo${random_string.storage.result}"
  resource_group_name      = local.rg_name
  location                 = local.p.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.tags
}

resource "azurerm_storage_container" "images" {
  name                  = "talos-images"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

# The VHD must be uploaded as page blob; this step uses the Azure CLI (az) with the
# storage account key, passed via environment - no additional role assignment required.
resource "terraform_data" "talos_vhd" {
  triggers_replace = [
    module.talos-image.disk_image_url,
    azurerm_storage_account.this.id,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/sh", "-c"]
    environment = {
      AZURE_STORAGE_ACCOUNT = azurerm_storage_account.this.name
      AZURE_STORAGE_KEY     = azurerm_storage_account.this.primary_access_key
    }
    command = <<-EOT
      set -eu
      tmpdir="$(mktemp -d)"
      trap 'rm -rf "$tmpdir"' EXIT
      curl -fsSL "${module.talos-image.disk_image_url}" | xz -d > "$tmpdir/talos.vhd"
      az storage blob upload \
        --auth-mode key \
        --container-name "${azurerm_storage_container.images.name}" \
        --name "${local.talos_blob}" \
        --file "$tmpdir/talos.vhd" \
        --type page \
        --overwrite true \
        --only-show-errors
    EOT
  }
}

resource "azurerm_image" "talos" {
  name                = "talos-${replace(local.cfg.vm.talos_version, ".", "-")}-${substr(module.talos-image.schematic_id, 0, 8)}"
  resource_group_name = local.rg_name
  location            = local.p.location
  hyper_v_generation  = "V2"
  tags                = local.tags

  os_disk {
    os_type      = "Linux"
    os_state     = "Generalized"
    storage_type = local.disk_type
    blob_uri     = "${azurerm_storage_account.this.primary_blob_endpoint}${azurerm_storage_container.images.name}/${local.talos_blob}"
  }

  depends_on = [terraform_data.talos_vhd]
}


# --- network ---

resource "azurerm_virtual_network" "this" {
  name                = "${local.cfg.demo.name}-vnet"
  address_space       = [local.cidr_vnet]
  location            = local.p.location
  resource_group_name = local.rg_name
  tags                = local.tags
}

resource "azurerm_subnet" "this" {
  name                 = "${local.cfg.demo.name}-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [local.cidr_subnet]
}

resource "azurerm_network_security_group" "this" {
  name                = "${local.cfg.demo.name}-nsg"
  location            = local.p.location
  resource_group_name = local.rg_name
  tags                = local.tags

  # demo: http (redirect, Let's Encrypt HTTP-01) and https on the LoadBalancer IP
  security_rule {
    name                       = "public-http-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "*"
    destination_address_prefix = local.lb_ip
  }

  # administration: Adminapp for the local administrator (Microgateway port 8443), restricted to admin IPs
  security_rule {
    name                         = "admin-iam-adminapp"
    priority                     = 105
    direction                    = "Inbound"
    access                       = "Allow"
    protocol                     = "Tcp"
    source_port_range            = "*"
    destination_port_range       = "8443"
    source_address_prefixes      = local.cfg.vm.admin_ips
    destination_address_prefix   = local.lb_ip
  }

  # administration: Talos API & Kubernetes API, restricted to admin IPs
  security_rule {
    name                         = "admin-talos-kubernetes-api"
    priority                     = 110
    direction                    = "Inbound"
    access                       = "Allow"
    protocol                     = "Tcp"
    source_port_range            = "*"
    destination_port_ranges      = ["50000", "6443"]
    source_address_prefixes      = local.cfg.vm.admin_ips
    destination_address_prefix   = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "this" {
  subnet_id                 = azurerm_subnet.this.id
  network_security_group_id = azurerm_network_security_group.this.id
}

resource "azurerm_public_ip" "admin" {
  name                = "${local.cfg.demo.name}-admin-ip"
  resource_group_name = local.rg_name
  location            = local.p.location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.tags
}

# DNS label of the demo public IP: unique per Azure region (across all customers) - checked during plan,
# so apply-1 fails before anything is created (check-dns-label.sh, Azure CLI)
data "external" "dns_label_check" {
  count   = local.dns_label == "" ? 0 : 1
  program = ["bash", "${path.module}/check-dns-label.sh", local.p.subscription_id, local.p.location,
             local.resource_group, "${local.cfg.demo.name}-lb-ip", local.dns_label]
}

resource "azurerm_public_ip" "lb" {
  name                = "${local.cfg.demo.name}-lb-ip"
  resource_group_name = local.rg_name
  location            = local.p.location
  allocation_method   = "Static"
  sku                 = "Standard"
  # DNS name <label>.<location>.cloudapp.azure.com (setting dns_label, default airlock-<demo name>, "" for none)
  domain_name_label   = local.dns_label == "" ? null : local.dns_label
  tags                = local.tags
}

resource "azurerm_network_interface" "this" {
  name                = "${local.cfg.demo.name}-nic"
  location            = local.p.location
  resource_group_name = local.rg_name
  tags                = local.tags

  # accelerated networking: Azure adds a Mellanox VF (eth1) under eth0; Talos tries to detach it
  # ("error enslaving/unslaving link eth1 ... operation not supported"), the link flaps about once a
  # minute and the node is unreachable most of the time - not needed for a single-node demo
  accelerated_networking_enabled = false

  ip_configuration {
    name                          = "primary"
    primary                       = true
    subnet_id                     = azurerm_subnet.this.id
    private_ip_address_allocation = "Static"
    private_ip_address            = local.node_ip
    public_ip_address_id          = azurerm_public_ip.admin.id
  }

  ip_configuration {
    name                          = "loadbalancer"
    subnet_id                     = azurerm_subnet.this.id
    private_ip_address_allocation = "Static"
    private_ip_address            = local.lb_ip
    public_ip_address_id          = azurerm_public_ip.lb.id
  }
}


# --- virtual machine ---

# Talos ignores it, but Azure requires an admin password
resource "random_password" "azure_placeholder" {
  length           = 32
  special          = true
  override_special = "_%@-"
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = "${local.cfg.demo.name}-controlplane-0"
  computer_name                   = "${local.cfg.demo.name}-cp0"
  resource_group_name             = local.rg_name
  location                        = local.p.location
  size                            = local.vm_size
  network_interface_ids           = [azurerm_network_interface.this.id]
  source_image_id                 = azurerm_image.talos.id
  admin_username                  = "talos"
  admin_password                  = random_password.azure_placeholder.result
  disable_password_authentication = false
  provision_vm_agent              = false
  allow_extension_operations      = false
  tags                            = local.tags

  os_disk {
    name                 = "${local.cfg.demo.name}-system"
    caching              = "ReadWrite"
    storage_account_type = local.disk_type
    disk_size_gb         = local.cfg.vm.disk_size_system
  }

  # managed boot diagnostics (serial console)
  boot_diagnostics {}
}

resource "azurerm_managed_disk" "data" {
  name                 = "${local.cfg.demo.name}-data"
  location             = local.p.location
  resource_group_name  = local.rg_name
  storage_account_type = local.disk_type
  create_option        = "Empty"
  disk_size_gb         = local.cfg.vm.disk_size_data
  tags                 = local.tags
}

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.this.id
  lun                = 0
  caching            = "ReadWrite"
}
