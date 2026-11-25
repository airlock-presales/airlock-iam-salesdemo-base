# Airlock IAM Salesdemo
# Phase: 3 - ArgoCD
#
# Task
# - Save project settings as configmap
# - Prepare licenses and pull secrets
# - IAM configuration from the instance repository (iam/iam-config.yaml) as configmap
# - Install ArgoCD
# - Create ArgoCD project and app-of-apps, which deploys everything else
#
# Output
# - None


module "config" {
    source = "../config"

    settings            = local.settings
    basedir             = var.basedir
}

# - namespace
resource "kubernetes_namespace_v1" "argocd" {
  metadata {
    name = "argocd"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
  wait_for_default_service_account = true
}

# - project settings, completed with the LoadBalancer pool from phase 1 (platform-specific)
data "terraform_remote_state" "infrastructure" {
  backend = "local"

  config = {
    path = "${module.config.settings.paths.state}/01-infrastructure.tfstate"
  }
}

locals {
  infra   = data.terraform_remote_state.infrastructure.outputs
  lb_pool = local.infra.lb_pool
  # fixed gateway address (PureLB annotation; in-cluster name resolution of the FQDN, e.g. ArgoCD
  # OIDC discovery): first address of the pool - range "a-b" or CIDR (network address skipped)
  gateway_ip = (strcontains(local.lb_pool, "/")
    ? cidrhost(local.lb_pool, tonumber(split("/", local.lb_pool)[1]) >= 31 ? 0 : 1)
    : split("-", local.lb_pool)[0])

  # IAM configuration from the instance repository; @@FQDN@@: redirect URIs of the OIDC clients
  # (string lists, no environment variables possible)
  iam_config_path = module.config.settings.paths.iam_config
  iam_config = (fileexists(local.iam_config_path)
    ? replace(file(local.iam_config_path), "@@FQDN@@", module.config.settings.demo.fqdn)
    : null)
  # server-side texts: iam/<app>-texts/*.properties (e.g. loginapp-texts/strings_en.properties),
  # configmap key <app>-texts.<file>, copied to <instance>/<app>-texts/ by init-config
  iam_dir   = dirname(local.iam_config_path)
  iam_texts = {
    for f in fileset(local.iam_dir, "*-texts/*.properties") :
      replace(f, "/", ".") => file("${local.iam_dir}/${f}")
  }
  # Loginapp UI customizations (design kit): iam/airlock-iam-loginapp-rest-ui-customizations.zip,
  # binary data of its own configmap iam-ui-customizations (max. ~750 KB), copied into the instance
  # by init-config
  iam_ui_zip_path = "${local.iam_dir}/airlock-iam-loginapp-rest-ui-customizations.zip"
  iam_ui_zip_data = (fileexists(local.iam_ui_zip_path)
    ? { "airlock-iam-loginapp-rest-ui-customizations.zip" = filebase64(local.iam_ui_zip_path) } : {})
  # configuration snippets (setting airlock_iam_config_snippets): iam/snippets/<file>, configmap key
  # snippet.<NN>.<file> (NN: position in the list, the import order), imported into the
  # configuration by init-config; @@FQDN@@ replaced as in the configuration
  iam_snippets_missing = [for f in module.config.settings.airlock.iam.config_snippets : f
                          if !fileexists("${local.iam_dir}/snippets/${f}")]
  iam_snippets = length(local.iam_snippets_missing) > 0 ? {} : {
    for i, f in module.config.settings.airlock.iam.config_snippets :
      format("snippet.%02d.%s", i + 1, f) => replace(file("${local.iam_dir}/snippets/${f}"), "@@FQDN@@", module.config.settings.demo.fqdn)
  }
  iam_config_data = local.iam_config == null ? {} : merge(local.iam_texts, local.iam_snippets, {
    "iam-config.yaml" = local.iam_config
  })
  # the configuration itself compressed in the configmap (a configmap holds at most 1 MiB; the YAML
  # configuration exceeds that, gzip reduces it about tenfold) - unpacked by the init container init-unpack
  iam_config_cm_data   = { for k, v in local.iam_config_data : k => v if k != "iam-config.yaml" }
  iam_config_cm_binary = local.iam_config == null ? {} : { "iam-config.yaml.gz" = base64gzip(local.iam_config) }

  project_settings = merge(module.config.settings, {
      # gateway certificate and key (tls_issuer provided) only for OpenTofu (secret gateway-tls-cert),
      # not in the configmap
      tls = {
          issuer     = module.config.settings.tls.issuer
          acme_email = module.config.settings.tls.acme_email
      }
      # hash of the IAM configuration: pod annotation, IAM restarts when the configuration changes
      airlock = merge(module.config.settings.airlock, {
          iam = merge(module.config.settings.airlock.iam, {
              config_hash = local.iam_config == null ? "" : sha256(jsonencode([local.iam_config_data, local.iam_ui_zip_data]))
          })
      })
      # Adminer automatic login: unguessable name of the user header (Microgateway identity
      # propagation), so the header can't be sent by clients bypassing the gateway
      tools = {
          adminer = {
              auth_header = "X-Auth-User-${random_string.adminer-auth-header.result}"
          }
      }
      kubernetes = merge(module.config.settings.kubernetes, {
          lb = {
              pool       = local.lb_pool
              subnet     = local.infra.lb_subnet
              gateway_ip = local.gateway_ip
          }
      })
  })
}

resource "random_string" "adminer-auth-header" {
  length  = 16
  upper   = false
  special = false
}

module "config-settings" {
    source = "./config-settings"
    depends_on          = [ kubernetes_namespace_v1.argocd ]

    settings            = local.project_settings
}

# - airlock product licenses
module "airlock-secrets" {
    source = "./airlock-secrets"
    depends_on          = [ kubernetes_namespace_v1.argocd ]

    settings            = module.config.settings
}

# - IAM configuration, copied into the instance by the init container init-config
resource "kubernetes_config_map_v1" "iam-config" {
    depends_on          = [ module.airlock-secrets ]   # namespace iam

    metadata {
      name        = "iam-config"
      namespace   = "iam"
    }
    data        = local.iam_config_cm_data
    binary_data = local.iam_config_cm_binary

    lifecycle {
      precondition {
        condition     = local.iam_config != null
        error_message = "IAM configuration ${local.iam_config_path} not found - run 'make init' (copies the template from the base repository)."
      }
      precondition {
        condition     = length(local.iam_snippets_missing) == 0
        error_message = "IAM configuration snippets not found in ${local.iam_dir}/snippets/: ${join(", ", local.iam_snippets_missing)} (setting airlock_iam_config_snippets)."
      }
    }
}

# - Loginapp UI customizations (design kit zip), own configmap because of its size; always created
#   (empty without zip), mounted into the init container init-config only
resource "kubernetes_config_map_v1" "iam-ui-customizations" {
    depends_on          = [ module.airlock-secrets ]   # namespace iam

    metadata {
      name        = "iam-ui-customizations"
      namespace   = "iam"
    }
    binary_data = local.iam_ui_zip_data

    lifecycle {
      precondition {
        condition     = length(jsonencode(local.iam_ui_zip_data)) < 1000000
        error_message = "${local.iam_ui_zip_path} is too large for a configmap (max. ~750 KB)."
      }
    }
}

# - argocd, project & app-of-apps
module "argocd" {
    source = "./argocd"
    depends_on          = [ module.config-settings, module.airlock-secrets, kubernetes_config_map_v1.iam-config,
                            kubernetes_config_map_v1.iam-ui-customizations ]

    settings            = local.project_settings
}
