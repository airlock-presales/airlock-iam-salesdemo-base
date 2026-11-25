# Salesdemo project configuration
#
# Source @ config/root/vars_config.tf - only edit there, then run 'make settings'

# --- set by tofuwrap ---

variable "basedir" {
    type = string
    description = "Instance directory (where tofuwrap was started)"
}

variable "demo_release" {
    type = string
    description = "Release (git tag or branch) of the salesdemo base repo, from file 'release' in instance directory"
}

# --- set in variables.auto.tfvars ---

variable "sec_state_passphrase" {
    type = string
    sensitive = true
    description = "Passphrase for OpenTofu state encryption"
    validation {
        condition = length(var.sec_state_passphrase) >= 16
        error_message = "sec_state_passphrase must be at least 16 characters long."
    }
}

variable "demo_name" {
    type = string
    validation {
        condition = can(regex("^[a-z0-9]([-a-z0-9]{0,30}[a-z0-9])?$", var.demo_name))
        error_message = "demo_name is required: lowercase letters, digits and '-', max. 32 characters."
    }
}

variable "demo_fqdn" {
    type = string
    validation {
        condition = var.demo_fqdn != ""
        error_message = "demo_fqdn is required."
    }
}

variable "tls_issuer" {
    type = string
    default = "internal"
    validation {
        condition = contains(["internal", "letsencrypt", "provided"], var.tls_issuer)
        error_message = "tls_issuer must be one of internal, letsencrypt, provided."
    }
}

# tls_issuer = "provided": certificate and key of the gateway, e.g. from a company or public CA
variable "tls_certificate" {
    description = "Gateway certificate (PEM): server certificate for demo_fqdn followed by the intermediate chain"
    type = string
    default = ""
    validation {
        condition = var.tls_issuer != "provided" || strcontains(var.tls_certificate, "-----BEGIN CERTIFICATE-----")
        error_message = "tls_certificate (PEM, server certificate followed by the chain) is required for tls_issuer = provided."
    }
}

variable "tls_private_key" {
    description = "Private key of the gateway certificate (PEM)"
    type = string
    sensitive = true
    default = ""
    validation {
        condition = var.tls_issuer != "provided" || can(regex("-----BEGIN ([A-Z]+ )?PRIVATE KEY-----", var.tls_private_key))
        error_message = "tls_private_key (PEM) is required for tls_issuer = provided."
    }
}

variable "tls_acme_email" {
    type = string
    default = ""
}

variable "sec_password_argocd" {
    type = string
    sensitive = true
    default = ""
}

variable "sec_data_key" {
    description = "Secret from which the keys protecting persistent data are derived (Airlock 2FA storage encryption, OATH OTP secrets, new-device cookie) - keep it: the same value restores the same keys after a reinstallation"
    type = string
    sensitive = true
    validation {
        condition = length(var.sec_data_key) >= 32
        error_message = "sec_data_key is required, min. 32 characters (e.g. openssl rand -base64 48)."
    }
}

variable "sec_password_iam" {
    description = "Initial password of the IAM administrators 'emergency' (medusa_admin) and 'admin' (medusa_user) - hashed by IAM at the first login"
    type = string
    sensitive = true
    validation {
        condition = length(var.sec_password_iam) > 0
        error_message = "sec_password_iam is required."
    }
}

variable "vm_timezone" {
    type = string
    default = ""
}

variable "vm_admin_ips" {
    type = list(string)
    description = "IP ranges allowed to access the Talos and Kubernetes API, required on cloud platforms"
    default = []
    validation {
        condition = contains(["local", "kvm"], var.platform) || length(var.vm_admin_ips) > 0
        error_message = "vm_admin_ips is required on cloud platforms."
    }
}

variable "vm_ntp_servers" {
    type = list(string)
    default = []
}

variable "platform" {
    type = string
    description = "Platform to deploy to, selects 01-infrastructure/platforms/<platform>"
    validation {
        condition = contains(["azure", "kvm", "local"], var.platform)
        error_message = "platform is required: one of azure, kvm, local."
    }
}

# --- platform-specific settings, only the one of the selected platform is required ---

variable "platform_local" {
    description = "VM created manually (e.g. VMware Workstation), booted from Talos ISO"
    type = object({
        ip        = string                       # IP address of the VM
        disk      = optional(string, "/dev/sda") # system disk device
        lb_pool   = string                       # LoadBalancer IP range, e.g. 192.168.1.200-192.168.1.219
        lb_subnet = string                       # subnet of the LoadBalancer IP range, e.g. 192.168.1.0/24
    })
    default = null
    validation {
        condition = var.platform != "local" || var.platform_local != null
        error_message = "platform_local must be set for platform 'local'."
    }
}

variable "platform_kvm" {
    description = "VM created on a KVM host via libvirt (ssh)"
    type = object({
        host      = string                       # KVM host name
        user      = string                       # user on KVM host
        pool      = optional(string, "default")  # libvirt storage pool for disks
        network   = optional(string, "default")  # libvirt network
        ip        = string                       # IP address of the VM (fixed by DHCP reservation for mac)
        mac       = string                       # MAC address of the VM
        dhcp_reservation = optional(bool, true)  # create the DHCP reservation in the libvirt-managed network
                                                 # (false: bridged network, reservation in its DHCP server)
        lb_pool   = string                       # LoadBalancer IP range or CIDR
        lb_subnet = string                       # subnet of the LoadBalancer IP range
        vcpu      = optional(number, 4)          # VM size: CPUs (2 is too little for the initial installation)
        memory    = optional(number, 8)          # VM size: memory in GiB
    })
    default = null
    validation {
        condition = var.platform != "kvm" || var.platform_kvm != null
        error_message = "platform_kvm must be set for platform 'kvm'."
    }
}

variable "platform_azure" {
    description = "VM created in Azure"
    type = object({
        subscription_id      = string
        location             = string            # Azure region, e.g. switzerlandnorth
        vm_size              = optional(string, "Standard_D4s_v5")  # 4 vCPU, 16 GiB (D2s_v5 with 2 vCPU is too little)
        resource_group       = optional(string)  # default salesdemo-<demo name>
        dns_label            = optional(string)  # DNS name of the demo public IP: <label>.<location>.cloudapp.azure.com
                                                 # (unique per region); default airlock-<demo name>, "" for none
        resource_group_existing = optional(bool, false)  # false: phase 1 creates the group (must not exist yet);
                                                         # true: use an existing group (resource_group required), kept by 'make remove'
    })
    default = null
    validation {
        condition = var.platform != "azure" || var.platform_azure != null
        error_message = "platform_azure must be set for platform 'azure'."
    }
    validation {
        condition = try(var.platform_azure.resource_group, null) == null || can(regex("^[-\\w._()]{0,89}[-\\w_()]$", var.platform_azure.resource_group))
        error_message = "platform_azure.resource_group: 1-90 letters, digits, '-', '_', '.', '(', ')', not ending with '.'."
    }
    validation {
        condition = try(var.platform_azure.dns_label == null || var.platform_azure.dns_label == "" || can(regex("^[a-z][a-z0-9-]{1,61}[a-z0-9]$", var.platform_azure.dns_label)), true)
        error_message = "platform_azure.dns_label: 3-63 lower-case letters, digits and '-', starting with a letter, not ending with '-' (or \"\" for none)."
    }
    validation {
        condition = !try(var.platform_azure.resource_group_existing, false) || try(var.platform_azure.resource_group, null) != null
        error_message = "platform_azure.resource_group_existing requires platform_azure.resource_group (name of the existing group)."
    }
}

variable "k8s_argocd_repo_url" {
    type = string
    validation {
        condition = var.k8s_argocd_repo_url != ""
        error_message = "k8s_argocd_repo_url is required."
    }
}

variable "k8s_argocd_repo_username" {
    type = string
    default = ""
}

variable "k8s_argocd_repo_password" {
    type = string
    sensitive = true
    default = ""
}

variable "k8s_argocd_repo_ssh_key" {
    type = string
    sensitive = true
    default = ""
}

variable "k8s_ghcr_pull" {
    description = "Credentials to pull the salesdemo images from ghcr.io (argocd-cli, qr-service); not needed if the packages are public"
    type = object({
        username = string
        token    = string   # classic personal access token with scope read:packages
    })
    sensitive = true
    default = null
}

variable "airlock_iam_license" {
    type = string
    sensitive = true
    default = ""
}

variable "airlock_mgw_license" {
    type = string
    sensitive = true
    default = ""
}

variable "airlock_iam_pull_username" {
    type = string
    default = ""
}

variable "airlock_iam_pull_password" {
    type = string
    sensitive = true
    default = ""
}

variable "airlock_iam_config_sync" {
    description = "Copy IAM configuration from git into the instance: changed, always, never"
    type = string
    default = "changed"
    validation {
        condition = contains(["changed", "always", "never"], var.airlock_iam_config_sync)
        error_message = "airlock_iam_config_sync must be one of changed, always, never."
    }
}

variable "airlock_iam_config_restore_users" {
    description = "Users allowed to restore the deployed IAM configuration from the portal (also need an administrator role and a second factor); empty: all"
    type = list(string)
    default = []
    validation {
        condition = alltrue([for u in var.airlock_iam_config_restore_users : can(regex("^[A-Za-z0-9._@+-]+$", u))])
        error_message = "airlock_iam_config_restore_users: usernames with letters, digits and . _ @ + - only."
    }
}

variable "airlock_iam_config_snippets" {
    description = "IAM configuration snippets (iam/snippets/<file> in the instance repository) imported into iam/iam-config.yaml at deployment, in this order"
    type = list(string)
    default = []
    validation {
        condition = alltrue([for f in var.airlock_iam_config_snippets : can(regex("^[A-Za-z0-9._-]+\\.ya?ml$", f))])
        error_message = "airlock_iam_config_snippets: file names in iam/snippets/ ending in .yaml or .yml, without directories."
    }
}

variable "airlock_iam_airlock2fa_recovery_info" {
    description = "Portal entry with instructions for recovering Airlock 2FA accounts on a new phone (requires the account recovery feature activated in the Futurae service)"
    type = bool
    default = false
}

variable "airlock_iam_admin_oidc" {
    description = "Optional OIDC client of this instance at an external OIDC provider (e.g. secure.ergon.ch), for an administrator login added to the IAM configuration (not used by the configuration template)"
    type = object({
        client_id     = string
        client_secret = string
    })
    sensitive = true
    default = null
}

variable "airlock_iam_sms_truesenses" {
    description = "Optional TrueSenses SMS gateway account and service URI, stored in the secret iam-credentials (/run/secrets/iam/truesenses-*); used only by an IAM snippet with a TrueSensesSmsGateway (not by the configuration template)"
    type = object({
        username    = string
        password    = string
        service_uri = optional(string, "https://truesenses.com/cgi-bin/smsgateway.cgi")
    })
    sensitive = true
    default = null
}

variable "airlock_iam_futurae" {
    description = "Futurae service for Airlock 2FA"
    type = object({
        service_id    = string
        auth_api_key  = string
        admin_api_key = string
    })
    sensitive = true
    nullable = false
}

variable "airlock_iam_pxl" {
    description = "PXL Vision identity proofing (test environment)"
    type = object({
        api_key    = string
        account_id = string
    })
    sensitive = true
    nullable = false
}

variable "airlock_iam_smtp" {
    description = "SMTP server for emails sent by IAM; not set: in-cluster Mailpit"
    type = object({
        host      = string
        port      = optional(number, 587)
        tls       = optional(string, "starttls")  # none, starttls, ssl
        username  = string                        # IAM always authenticates
        password  = string
        sender    = string                        # sender address, e.g. iam@example.com
    })
    sensitive = true
    default = null
    validation {
        condition = var.airlock_iam_smtp == null ? true : contains(["none", "starttls", "ssl"], var.airlock_iam_smtp.tls)
        error_message = "airlock_iam_smtp.tls must be one of none, starttls, ssl."
    }
}

# -----------------

locals {
    settings = {
        demo = {
            name = var.demo_name
            fqdn = var.demo_fqdn
            release = var.demo_release
        }
        tls = {
            issuer = var.tls_issuer
            acme_email = var.tls_acme_email
            certificate = var.tls_certificate
            private_key = var.tls_private_key
        }
        security = {
            password_argocd = var.sec_password_argocd
            password_iam = var.sec_password_iam
            data_key = var.sec_data_key
        }
        vm = {
            timezone = var.vm_timezone
            admin_ips = var.vm_admin_ips
            ntp_servers = var.vm_ntp_servers
        }
        platform = var.platform
        kubernetes = {
            argocd = {
                repository = {
                    url = var.k8s_argocd_repo_url
                    username = var.k8s_argocd_repo_username
                    password = var.k8s_argocd_repo_password
                    ssh_key = var.k8s_argocd_repo_ssh_key
                }
            }
            ghcr_pull = var.k8s_ghcr_pull
        }
        airlock = {
            iam = {
                license = var.airlock_iam_license
                pull_username = var.airlock_iam_pull_username
                pull_password = var.airlock_iam_pull_password
                config_sync = var.airlock_iam_config_sync
                config_restore_users = var.airlock_iam_config_restore_users
                config_snippets = var.airlock_iam_config_snippets
                airlock2fa_recovery_info = var.airlock_iam_airlock2fa_recovery_info
                smtp = var.airlock_iam_smtp
                admin_oidc = var.airlock_iam_admin_oidc
                sms_truesenses = var.airlock_iam_sms_truesenses
                futurae = var.airlock_iam_futurae
                pxl = var.airlock_iam_pxl
            }
            mgw = {
                license = var.airlock_mgw_license
            }
        }
    }
}
