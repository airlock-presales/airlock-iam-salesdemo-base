provider "azurerm" {
  subscription_id = var.platform_azure.subscription_id
  # existing resource group: the account may only have rights on that group - registering resource
  # providers (Microsoft.Compute, .Network, .Storage) needs subscription rights, so they must already be
  # registered (usual in a subscription prepared by its owner); otherwise the provider default
  resource_provider_registrations = try(var.platform_azure.resource_group_existing, false) ? "none" : null
  features {}
}
