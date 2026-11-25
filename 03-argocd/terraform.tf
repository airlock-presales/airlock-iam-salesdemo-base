terraform {
  required_version = ">= 1.9.0"

  # state lives in the instance directory, encrypted with the instance's passphrase
  backend "local" {
    path = "${var.basedir}/state/03-argocd.tfstate"
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
    helm = {
      source  = "hashicorp/helm"
      version = "3.3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.4"
    }
    pkcs12 = {
      source  = "chilicat/pkcs12"
      version = "~> 0.0.6"
    }
  }
}
