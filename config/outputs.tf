output "settings" {
    value = {
        demo = {
            name = var.settings.demo.name
            fqdn = var.settings.demo.fqdn
            release = var.settings.demo.release
        }
        tls = {
            # cert-manager ClusterIssuer for the gateway certificate; "provided": certificate from the
            # settings (secret created by OpenTofu, no cert-manager Certificate)
            issuer = (var.settings.tls.issuer == "internal" ? "cluster-ca-issuer"
                : var.settings.tls.issuer)
            acme_email = var.settings.tls.acme_email
            certificate = var.settings.tls.certificate
            private_key = var.settings.tls.private_key
        }
        security = {
            password_argocd = var.settings.security.password_argocd
            password_iam = var.settings.security.password_iam
            data_key = var.settings.security.data_key
        }
        vm = {
            talos_version = local.talos_version
            disk_size_system = local.disk_size_system
            disk_size_data = local.disk_size_data
            timezone = var.settings.vm.timezone != "" ? var.settings.vm.timezone : local.vm_timezone
            admin_ips = var.settings.vm.admin_ips
            ntp_servers = length(var.settings.vm.ntp_servers) > 0 ? var.settings.vm.ntp_servers : local.vm_ntp_servers
        }
        platform = var.settings.platform
        kubernetes = {
            version = local.k8s_version
            argocd = {
                repository = {
                    url = var.settings.kubernetes.argocd.repository.url
                    username = var.settings.kubernetes.argocd.repository.username
                    password = var.settings.kubernetes.argocd.repository.password
                    ssh_key = var.settings.kubernetes.argocd.repository.ssh_key
                }
            }
            ghcr_pull = var.settings.kubernetes.ghcr_pull
        }
        paths = {
            # instance directory: generated files and (encrypted) tofu state
            output = "${var.basedir}/output"
            state = "${var.basedir}/state"
            # IAM configuration of the instance (copied from the template iam/ by 'make init')
            iam_config = "${var.basedir}/iam/iam-config.yaml"
            templates = "${path.module}/../data/templates"
        }
        airlock = {
            iam = {
                license = var.settings.airlock.iam.license
                pull_username = var.settings.airlock.iam.pull_username
                pull_password = var.settings.airlock.iam.pull_password
                config_sync = var.settings.airlock.iam.config_sync
                config_restore_users = var.settings.airlock.iam.config_restore_users
                config_snippets = var.settings.airlock.iam.config_snippets
                airlock2fa_recovery_info = var.settings.airlock.iam.airlock2fa_recovery_info
                # SMTP server; not set: in-cluster Mailpit (no TLS, accepts any credentials)
                smtp = var.settings.airlock.iam.smtp != null ? var.settings.airlock.iam.smtp : {
                    host = "mailpit.mailpit.svc.cluster.local"
                    port = 1025
                    tls = "none"
                    username = "iam"
                    password = "mailpit"
                    sender = "iam@${var.settings.demo.fqdn}"
                }
                admin_oidc = var.settings.airlock.iam.admin_oidc
                sms_truesenses = var.settings.airlock.iam.sms_truesenses
                futurae = var.settings.airlock.iam.futurae
                pxl = var.settings.airlock.iam.pxl
            }
            mgw = {
                license = var.settings.airlock.mgw.license
            }
        }
    }
}
