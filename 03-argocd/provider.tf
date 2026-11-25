data "terraform_remote_state" "talos" {
  backend = "local"

  config = {
    path = "${module.config.settings.paths.state}/02-talos.tfstate"
  }
}

locals {
  kubeconfig = yamldecode( data.terraform_remote_state.talos.outputs.kubeconfig_raw )

  cluster = local.kubeconfig.clusters[0].cluster
  user    = local.kubeconfig.users[0].user
}

provider "kubernetes" {
  host = local.cluster.server

  cluster_ca_certificate = base64decode( local.cluster["certificate-authority-data"] )
  client_certificate     = base64decode( local.user["client-certificate-data"] )
  client_key             = base64decode( local.user["client-key-data"] )
}

provider "helm" {
  kubernetes = {
    host = local.cluster.server

    cluster_ca_certificate = base64decode( local.cluster["certificate-authority-data"] )
    client_certificate     = base64decode( local.user["client-certificate-data"] )
    client_key             = base64decode( local.user["client-key-data"] )
  }
}
