output "kubernetes_endpoint" {
  value = "https://${local.endpoint_ip}:6443"
}

output "public_ip" {
  value = local.endpoint_ip
}

output "kubeconfig" {
  description = "Raw kubeconfig consumed by layer 3. Sensitive because it contains client credentials."
  value       = local.kubeconfig_raw
  sensitive   = true
}

output "talosconfig" {
  description = "talosctl client configuration."
  value       = data.talos_client_configuration.client_config.talos_config
  sensitive   = true
}
