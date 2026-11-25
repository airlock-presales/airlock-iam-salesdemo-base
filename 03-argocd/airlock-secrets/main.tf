# Task
# - Create namespaces
# - Create secrets with IAM & Microgateway licenses
# - Create IAM image pull secret
# - Create Microgateway session store (Valkey) password
# - Create IAM database credentials and local administrator
# - Create IAM credentials (SMTP, ...), referenced in the IAM config with [FILE] or as variables
# - Create OIDC provider signing key (IAM) and OIDC client secrets (Mailpit, ArgoCD, ArgoCD gateway, Headlamp, Adminer)
# - Create IAM state repository (Valkey) password
# - Create Mailpit web UI credentials
# - Create pull secret for the salesdemo images on ghcr.io (optional)
#
# Output
# - None


resource "kubernetes_namespace_v1" "iam" {
  metadata {
    name = "iam"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "kubernetes_namespace_v1" "mgw" {
  metadata {
    name = "airlock-microgateway-system"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "kubernetes_secret_v1" "iam-license" {
    metadata {
      name        = "airlock-iam-license"
      namespace   = kubernetes_namespace_v1.iam.metadata[0].name
    }
    data = {
      "license.txt" = var.settings.airlock.iam.license
    }
}

resource "kubernetes_secret_v1" "mgw-license" {
    metadata {
      name        = "airlock-microgateway-license"
      namespace   = kubernetes_namespace_v1.mgw.metadata[0].name
    }
    data = {
      "microgateway-license.txt" = var.settings.airlock.mgw.license
    }
}

locals {
  pull_secret = format( "{\"auths\":{\"quay.io\":{\"username\":\"%s\",\"password\":\"%s\",\"auth\":\"%s\"}}}", var.settings.airlock.iam.pull_username, var.settings.airlock.iam.pull_password, base64encode( "${var.settings.airlock.iam.pull_username}:${var.settings.airlock.iam.pull_password}" ))
}

resource "kubernetes_secret_v1" "iam-pull" {
    metadata {
      name        = "airlock-iam-pull"
      namespace   = kubernetes_namespace_v1.iam.metadata[0].name
    }
    data = {
      ".dockerconfigjson" = local.pull_secret
    }
    type = "kubernetes.io/dockerconfigjson"
}


resource "kubernetes_namespace_v1" "gateway" {
  metadata {
    name = "airlock-gateway"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

# Session store password, used by Valkey and Microgateway (key name required by RedisProvider)
resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "redis-password" {
    metadata {
      name        = "redis-password"
      namespace   = kubernetes_namespace_v1.gateway.metadata[0].name
    }
    data = {
      "redis.password" = random_password.redis.result
    }
}

# IAM database credentials, used by MariaDB (operator) and IAM
resource "random_password" "iam-db" {
  for_each = toset(["password", "root-password"])
  length   = 32
  special  = false
}

resource "kubernetes_secret_v1" "iam-db" {
    metadata {
      name        = "iam-db"
      namespace   = kubernetes_namespace_v1.iam.metadata[0].name
    }
    data = {
      "username"      = "iam"
      "password"      = random_password.iam-db["password"].result
      "root-password" = random_password.iam-db["root-password"].result
    }
}

# IAM administrators 'emergency' (emergency administrator in medusa_admin) and 'admin' (realm
# administrator in medusa_user), created by the IAM init container if missing. The password is stored in cleartext
# and hashed by IAM at the first login (legacy hash function IdentityPasswordHash).
resource "kubernetes_secret_v1" "iam-admin" {
    metadata {
      name        = "iam-admin"
      namespace   = kubernetes_namespace_v1.iam.metadata[0].name
    }
    data = {
      "username" = "admin"
      "password" = var.settings.security.password_iam
      # technical administrator selfreg-lookup (created by init_db)
      "selfreg-lookup-password" = random_password.iam-selfreg-lookup.result
    }
}

# technical administrator selfreg-lookup: Adminapp REST API, used by the self-registration flow
resource "random_password" "iam-selfreg-lookup" {
  length  = 32
  special = false
}

# IAM state repository: Valkey in namespace iam (no persistence), password for Valkey and IAM
resource "random_password" "iam-valkey" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "iam-valkey" {
    metadata {
      name        = "iam-valkey"
      namespace   = kubernetes_namespace_v1.iam.metadata[0].name
    }
    data = {
      "valkey.password" = random_password.iam-valkey.result
    }
}


# IAM credentials for external services, mounted as files to /run/secrets/iam
locals {
  smtp = var.settings.airlock.iam.smtp
}

# Keys referenced in the IAM configuration (replacing the keys of the configuration template),
# base64 encoded - encryption: 256 bit, HMAC: 512 bit. Random per installation: they only protect
# short-lived data (sessions, tickets).
resource "random_bytes" "iam-key" {
  for_each = {
    "adminapp-service-container-secret" = 32
    "adminapp-sso-encryption-key" = 32
    "adminapp-sso-hmac-key"       = 64
    "demoapp-jwt-encryption-key"  = 32
    "demoapp-jwt-hmac-key"        = 64
    "loginapp-encryption-key"     = 32
    "loginapp-hmac-key"           = 64
  }
  length = each.value
}

# Keys protecting persistent data, derived from the setting sec_data_key: the same settings give the
# same keys, so a database backup stays readable after a reinstallation (no key backup needed).
locals {
  data_key = var.settings.security.data_key
  # Airlock 2FA storage encryption (database): exactly 96 bytes, base64 (128 characters) - 192 hex
  # characters of SHA-512 hashes, converted to base64 (3 hex characters = 12 bits = 2 characters)
  b64_alphabet   = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
  airlock2fa_hex = join("", [
    sha512("${local.data_key}:airlock2fa-storage-secret:1"),
    substr(sha512("${local.data_key}:airlock2fa-storage-secret:2"), 0, 64),
  ])
  derived_keys = {
    "airlock2fa-storage-secret" = join("", [for i in range(64) : format("%s%s",
      substr(local.b64_alphabet, floor(parseint(substr(local.airlock2fa_hex, i * 3, 3), 16) / 64), 1),
      substr(local.b64_alphabet, parseint(substr(local.airlock2fa_hex, i * 3, 3), 16) % 64, 1))])
    # new-device cookie (browsers): exactly 32 bytes, base64 (44 characters)
    "loginapp-new-device-key"   = base64sha256("${local.data_key}:loginapp-new-device-key")
    # OATH OTP: password encrypting the users' token secrets (database), 32 bytes, base64
    "oath-otp-secret"           = base64sha256("${local.data_key}:oath-otp-secret")
  }
}

# OIDC provider (Loginapp authorization server 'demo'): ID token signing key, PKCS#12 keystore
# (IAM has no built-in key generation; the certificate only serves as keystore entry)
resource "tls_private_key" "iam-oidc-signing" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "iam-oidc-signing" {
  private_key_pem       = tls_private_key.iam-oidc-signing.private_key_pem
  validity_period_hours = 87600   # 10 years
  allowed_uses          = ["digital_signature"]

  subject {
    common_name = "Airlock IAM OIDC ID Token Signing (${var.settings.demo.name})"
  }
}

resource "random_password" "iam-oidc-keystore" {
  length  = 24
  special = false
}

resource "pkcs12_from_pem" "iam-oidc-signing" {
  password        = random_password.iam-oidc-keystore.result
  cert_pem        = tls_self_signed_cert.iam-oidc-signing.cert_pem
  private_key_pem = tls_private_key.iam-oidc-signing.private_key_pem
}

resource "kubernetes_secret_v1" "iam-credentials" {
    metadata {
      name        = "iam-credentials"
      namespace   = kubernetes_namespace_v1.iam.metadata[0].name
    }
    data = merge({
      "smtp-host"     = local.smtp.host
      "smtp-port"     = tostring(local.smtp.port)
      # IAM SMTP server: protocol SMTP (optionally with STARTTLS) or SMTPS
      "smtp-protocol" = local.smtp.tls == "ssl" ? "SMTPS" : "SMTP"
      "smtp-starttls" = tostring(local.smtp.tls == "starttls")
      "smtp-username" = local.smtp.username
      "smtp-password" = local.smtp.password
      "smtp-sender"   = local.smtp.sender
      # administrator login at an external OIDC provider (optional, empty if not set)
      "admin-oidc-client-id"     = try(var.settings.airlock.iam.admin_oidc.client_id, "")
      "admin-oidc-client-secret" = try(var.settings.airlock.iam.admin_oidc.client_secret, "")
      # SMS gateway TrueSenses (optional, empty if not set; used only by an IAM snippet)
      "truesenses-username" = try(var.settings.airlock.iam.sms_truesenses.username, "")
      "truesenses-password" = try(var.settings.airlock.iam.sms_truesenses.password, "")
      "truesenses-service-uri" = try(var.settings.airlock.iam.sms_truesenses.service_uri, "")
      # Airlock 2FA: Futurae service
      "futurae-service-id"    = var.settings.airlock.iam.futurae.service_id
      "futurae-auth-api-key"  = var.settings.airlock.iam.futurae.auth_api_key
      "futurae-admin-api-key" = var.settings.airlock.iam.futurae.admin_api_key
      # identity proofing: PXL Vision
      "pxl-api-key"    = var.settings.airlock.iam.pxl.api_key
      "pxl-account-id" = var.settings.airlock.iam.pxl.account_id
      # self-registration: technical administrator selfreg-lookup (ScriptSecret)
      "selfreg-lookup-password" = random_password.iam-selfreg-lookup.result
      # OIDC provider: ID token signing keystore (password for keystore and key)
      "oidc-signing-password" = random_password.iam-oidc-keystore.result
      # OIDC client mailpit (Microgateway): client secret and ID token claim mailpit_authorization,
      # forwarded by Microgateway as Authorization header to Mailpit (web UI basic authentication)
      "mailpit-oidc-client-secret" = random_password.mailpit-oidc.result
      "mailpit-authorization"      = "Basic ${base64encode("admin:${random_password.mailpit.result}")}"
      # OIDC client argocd (ArgoCD server)
      "argocd-oidc-client-secret"  = random_password.argocd-oidc.result
      # OIDC client argocd-gw (Microgateway in front of ArgoCD)
      "argocd-gw-oidc-client-secret" = random_password.argocd-gw-oidc.result
      # OIDC client headlamp (Microgateway in front of Headlamp)
      "headlamp-oidc-client-secret"  = random_password.headlamp-oidc.result
      # OIDC client adminer (Microgateway in front of Adminer)
      "adminer-oidc-client-secret"   = random_password.adminer-oidc.result
      # state repository (Valkey in namespace iam)
      "valkey-password"              = random_password.iam-valkey.result
    }, { for name, key in random_bytes.iam-key : name => key.base64 }, local.derived_keys)
    binary_data = {
      "oidc-signing.p12" = pkcs12_from_pem.iam-oidc-signing.result
    }
}


# Mailpit: catches emails sent by IAM (if no SMTP server is set), web UI with basic authentication
# (credentials propagated by Microgateway from the IAM ID token, see mailpit-authorization)
resource "kubernetes_namespace_v1" "mailpit" {
  metadata {
    name = "mailpit"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "random_password" "mailpit" {
  length  = 24
  special = false
}

resource "kubernetes_secret_v1" "mailpit-ui-auth" {
    metadata {
      name        = "mailpit-ui-auth"
      namespace   = kubernetes_namespace_v1.mailpit.metadata[0].name
    }
    data = {
      "username" = "admin"
      "password" = random_password.mailpit.result
      "ui-auth"  = "admin:${random_password.mailpit.result}"
    }
}

# Mailpit web UI behind Microgateway (OIDC relying party, client mailpit at the IAM authorization server)
resource "random_password" "mailpit-oidc" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "mailpit-oidc-client" {
    metadata {
      name        = "mailpit-oidc-client"
      namespace   = kubernetes_namespace_v1.mailpit.metadata[0].name
    }
    data = {
      "client.secret" = random_password.mailpit-oidc.result
    }
}


# ArgoCD login with IAM (OIDC client argocd at the IAM authorization server 'demo'); referenced
# in argocd-cm oidc.config as $argocd-oidc-iam:clientSecret (label part-of: argocd required)
resource "random_password" "argocd-oidc" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "argocd-oidc-iam" {
    metadata {
      name        = "argocd-oidc-iam"
      namespace   = "argocd"
      labels = {
        "app.kubernetes.io/part-of" = "argocd"
      }
    }
    data = {
      "clientSecret" = random_password.argocd-oidc.result
    }
}

# Microgateway in front of ArgoCD: OIDC relying party (client argocd-gw), key client.secret
resource "random_password" "argocd-gw-oidc" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "argocd-gw-oidc-client" {
    metadata {
      name        = "argocd-gw-oidc-client"
      namespace   = "argocd"
    }
    data = {
      "client.secret" = random_password.argocd-gw-oidc.result
    }
}


# Headlamp behind Microgateway: OIDC relying party (client headlamp at the IAM authorization server
# 'demo'); Headlamp itself uses its service account (cluster-admin) for all users
resource "kubernetes_namespace_v1" "headlamp" {
  metadata {
    name = "headlamp"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

resource "random_password" "headlamp-oidc" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "headlamp-oidc-client" {
    metadata {
      name        = "headlamp-oidc-client"
      namespace   = kubernetes_namespace_v1.headlamp.metadata[0].name
    }
    data = {
      "client.secret" = random_password.headlamp-oidc.result
    }
}


# Adminer behind Microgateway: OIDC relying party (client adminer at the IAM authorization server 'demo')
resource "kubernetes_namespace_v1" "adminer" {
  metadata {
    name = "adminer"

    labels = {
      "app.kubernetes.io/managed-by" = "opentofu"
    }
  }
}

# Adminer automatic login (plugin login-auth-proxy): IAM database account
resource "kubernetes_secret_v1" "adminer-db" {
    metadata {
      name        = "adminer-db"
      namespace   = kubernetes_namespace_v1.adminer.metadata[0].name
    }
    data = {
      "username" = "iam"
      "password" = random_password.iam-db["password"].result
    }
}

resource "random_password" "adminer-oidc" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "adminer-oidc-client" {
    metadata {
      name        = "adminer-oidc-client"
      namespace   = kubernetes_namespace_v1.adminer.metadata[0].name
    }
    data = {
      "client.secret" = random_password.adminer-oidc.result
    }
}


# Pull secret for the salesdemo images on ghcr.io (argocd-cli, qr-service) - only if the
# packages are not public (setting k8s_ghcr_pull). The deployments always reference it.
locals {
  ghcr = var.settings.kubernetes.ghcr_pull
  # only whether the setting is present is used as key, not the credentials
  ghcr_namespaces = nonsensitive(local.ghcr == null) ? [] : ["argocd", kubernetes_namespace_v1.iam.metadata[0].name]
}

resource "kubernetes_secret_v1" "ghcr-pull" {
    for_each = toset(local.ghcr_namespaces)

    metadata {
      name        = "ghcr-pull"
      namespace   = each.value
    }
    data = {
      ".dockerconfigjson" = jsonencode({
        auths = {
          "ghcr.io" = {
            username = local.ghcr.username
            password = local.ghcr.token
            auth     = base64encode("${local.ghcr.username}:${local.ghcr.token}")
          }
        }
      })
    }
    type = "kubernetes.io/dockerconfigjson"
}


# Gateway certificate provided in the settings (tls_issuer = "provided"): TLS secret used by the
# gateway listeners (same name cert-manager uses otherwise; the microgateway package then drops its
# cert-manager Certificate). Checks: PEM readable, server certificate not expired (warning 30 days
# before). The DNS names are not checked (not provided by the tls_certificate data source).
locals {
  tls_provided = var.settings.tls.issuer == "provided"
}

data "tls_certificate" "gateway" {
  count   = local.tls_provided ? 1 : 0
  content = var.settings.tls.certificate
}

resource "kubernetes_secret_v1" "gateway-tls" {
  count = local.tls_provided ? 1 : 0

  metadata {
    name      = "gateway-tls-cert"
    namespace = kubernetes_namespace_v1.gateway.metadata[0].name
  }
  type = "kubernetes.io/tls"
  data = {
    "tls.crt" = var.settings.tls.certificate
    "tls.key" = var.settings.tls.private_key
  }

  lifecycle {
    precondition {
      condition     = timecmp(data.tls_certificate.gateway[0].certificates[0].not_after, plantimestamp()) > 0
      error_message = "tls_certificate has expired (not after ${data.tls_certificate.gateway[0].certificates[0].not_after})."
    }
  }
}

check "gateway_certificate_expiry" {
  assert {
    condition = (!local.tls_provided ? true
      : timecmp(data.tls_certificate.gateway[0].certificates[0].not_after, timeadd(plantimestamp(), "720h")) > 0)
    error_message = "tls_certificate expires within 30 days - put a renewed certificate into the settings and run make apply-3."
  }
}

