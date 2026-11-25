# Task
# - Store Salesdemo project settings in a configmap, read by the apply-config.sh
#   scripts of the ArgoCD applications (lovely plugin).
#   Contains secrets in plaintext - by design, see ANALYSIS.md.
#
# Output
# - None


resource "kubernetes_config_map_v1" "project-settings" {
    metadata {
      name        = "project-settings"
      namespace   = "argocd"
    }
    data = {
      "settings" = yamlencode( var.settings )
    }
}
