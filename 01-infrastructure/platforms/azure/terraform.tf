terraform {
  required_version = ">= 1.9.0"

  # state lives in the instance directory, encrypted with the instance's passphrase
  backend "local" {
    path = "${var.basedir}/state/01-infrastructure.tfstate"
  }

  encryption {
    key_provider "pbkdf2" "salesdemo" {
      passphrase = var.sec_state_passphrase
    }
    method "aes_gcm" "salesdemo" {
      keys = key_provider.pbkdf2.salesdemo
    }
    state {
      method   = method.aes_gcm.salesdemo
      enforced = true
    }
    plan {
      method   = method.aes_gcm.salesdemo
      enforced = true
    }
  }

  required_providers {
    talos = {
      source  = "siderolabs/talos"
      version = "0.12.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "5.11.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    external = {
      source  = "hashicorp/external"
      version = "2.3.5"
    }
  }
}
