# Task
# - Create argocd-secret with admin password
# - Use Helm to install ArgoCD (initial installation only, ArgoCD manages itself afterwards)
# - Create secret to access repository
# - Use Helm to create ArgoCD project and app-of-apps
#
# Output
# - None


locals {
  argocd_package = "${path.module}/../../applications/packages/argocd/argocd"
  argocd_chart   = yamldecode(file("${local.argocd_package}/kustomization.yaml")).helmCharts[0]

  repo = var.settings.kubernetes.argocd.repository
}

# Admin password: argocd-secret is replaced only if the password changes,
# as bcrypt() returns a different hash on each run. ArgoCD adds its own keys.
resource "terraform_data" "argocd-password" {
  input = sha256(var.settings.security.password_argocd)
}

resource "kubernetes_secret_v1" "argocd-secret" {
  metadata {
    name      = "argocd-secret"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name"    = "argocd-secret"
      "app.kubernetes.io/part-of" = "argocd"
    }
  }
  # without password, ArgoCD generates one in secret argocd-initial-admin-secret
  data = var.settings.security.password_argocd == "" ? {} : {
    "admin.password"      = bcrypt(var.settings.security.password_argocd)
    "admin.passwordMtime" = plantimestamp()
  }

  lifecycle {
    ignore_changes       = [data]
    replace_triggered_by = [terraform_data.argocd-password]
  }
}

# Deploy ArgoCD - same chart and values as the self-managing application 'argocd'
resource "helm_release" "argocd" {
  depends_on = [kubernetes_secret_v1.argocd-secret]

  name       = "argocd"
  repository = local.argocd_chart.repo
  chart      = local.argocd_chart.name
  version    = local.argocd_chart.version
  namespace  = var.namespace

  values = [
    replace(replace(replace(file("${local.argocd_package}/values.yaml"),
      "@@FQDN@@", var.settings.demo.fqdn),
      "@@GATEWAY_IP@@", var.settings.kubernetes.lb.gateway_ip),
      "@@OIDC_SKIP_VERIFY@@", tostring(var.settings.tls.issuer != "letsencrypt"))
  ]

  wait    = true
  timeout = 600

  # ArgoCD manages itself after the initial installation
  lifecycle {
    ignore_changes = all
  }
}

resource "kubernetes_secret_v1" "argocd-repo" {
  metadata {
    name      = "salesdemo-repo"
    namespace = var.namespace
    labels = {
      "argocd.argoproj.io/secret-type" = "repository"
    }
  }
  data = merge(
    { url = local.repo.url },
    local.repo.ssh_key != "" ? { sshPrivateKey = local.repo.ssh_key } : {},
    local.repo.password != "" ? { username = local.repo.username, password = local.repo.password } : {},
  )
}

# ArgoCD project and app-of-apps. Uses helm instead of kubernetes_manifest, as the latter
# requires the ArgoCD CRDs at plan time.
resource "helm_release" "bootstrap" {
  depends_on = [helm_release.argocd, kubernetes_secret_v1.argocd-repo]

  name       = "bootstrap"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argocd-apps"
  version    = "2.0.8"
  namespace  = var.namespace

  values = [
    yamlencode({
      projects = {
        salesdemo = {
          namespace   = var.namespace
          description = "Salesdemo applications"
          sourceRepos = [local.repo.url]
          destinations = [{
            server    = "https://kubernetes.default.svc"
            namespace = "*"
          }]
          clusterResourceWhitelist   = [{ group = "*", kind = "*" }]
          namespaceResourceWhitelist = [{ group = "*", kind = "*" }]
        }
      }
      applications = {
        bootstrap = {
          namespace  = var.namespace
          finalizers = ["resources-finalizer.argocd.argoproj.io"]
          project    = "salesdemo"
          source = {
            repoURL        = local.repo.url
            targetRevision = var.settings.demo.release
            path           = "applications/argocd/bootstrap"
            plugin = {
              name = "lovely"
              # hash of the project settings: a settings change changes this application, so ArgoCD
              # renders it (and, through apply-config.sh, all applications) again
              env = [{
                name  = "SETTINGS_HASH"
                value = substr(sha256(yamlencode(var.settings)), 0, 16)
              }]
              parameters = [{
                name   = "lovely_preprocessors"
                string = "bash ./apply-config.sh"
              }]
            }
          }
          destination = {
            server    = "https://kubernetes.default.svc"
            namespace = var.namespace
          }
          syncPolicy = {
            automated = {
              prune    = true
              selfHeal = true
            }
            # a child application briefly Degraded in its first sync (e.g. gateway-api) fails the
            # sync of a wave; constant short retries instead of an exponential backoff up to 5m
            # (observed: ~5 min per wave), more attempts for all waves of an installation
            retry = {
              limit = 20
              backoff = {
                duration    = "10s"
                factor      = 1
                maxDuration = "10s"
              }
            }
          }
        }
      }
    })
  ]
}
