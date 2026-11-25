output "kubeconfig_raw" {
  description = "Raw kubeconfig consumed by layer 3. Sensitive because it contains client credentials."
  value = module.bootstrap.kubeconfig
  sensitive   = true
}
