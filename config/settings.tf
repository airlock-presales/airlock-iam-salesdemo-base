# Salesdemo instance settings, as assembled in vars_config.tf
#
# Only values which differ between instances are settings.
# Everything else is fixed by the release, see defaults.tf.

variable "settings" {
    type        = object({
        demo = object({
            name =                  string
            fqdn =                  string
            release =               string
        })

        tls = object({
            issuer =                string
            acme_email =            string
            certificate =           string
            private_key =           string
        })

        security = object({
            password_argocd =       string
            password_iam =          string
            data_key =              string
        })

        vm = object({
            timezone =              string
            admin_ips =             list(string)
            ntp_servers =           list(string)
        })

        platform =                  string

        kubernetes = object({
            argocd =                object({
                repository =        object({
                    url =           string
                    username =      string
                    password =      string
                    ssh_key =       string
                })
            })
            ghcr_pull =             object({
                username =          string
                token =             string
            })
        })

        airlock = object({
            iam =                   object({
                license =           string
                pull_username =     string
                pull_password =     string
                config_sync =       string
                config_restore_users = list(string)
                config_snippets = list(string)
                airlock2fa_recovery_info = bool
                smtp =              object({
                    host =          string
                    port =          number
                    tls =           string
                    username =      string
                    password =      string
                    sender =        string
                })
                admin_oidc =        object({
                    client_id =     string
                    client_secret = string
                })
                sms_truesenses =    object({
                    username =      string
                    password =      string
                    service_uri =   string
                })
                futurae =           object({
                    service_id =    string
                    auth_api_key =  string
                    admin_api_key = string
                })
                pxl =               object({
                    api_key =       string
                    account_id =    string
                })
            })
            mgw =                   object({
                license =           string
            })
        })
    })
}
