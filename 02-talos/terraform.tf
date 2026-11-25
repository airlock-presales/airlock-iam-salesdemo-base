terraform {
  required_version = ">= 1.9.0"

  # state lives in the instance directory, encrypted with the instance's passphrase
  backend "local" {
    path = "${var.basedir}/state/02-talos.tfstate"
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
    remote_state_data_sources {
      default {
        method = method.aes_gcm.salesdemo
      }
    }
  }

  required_providers {
    talos = {
      source  = "siderolabs/talos"
      version = "0.12.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}
