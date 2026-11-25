# Airlock IAM Salesdemo - architecture overview

An overview for integrators: which components make up a salesdemo instance, where they run and how they work together. Details are in the [internals](README.md) of this repository and in the [instance documentation](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template) (setup, settings, usage).

**In short:** one virtual machine runs Talos Linux with a single-node Kubernetes cluster. OpenTofu, started with `make` from the instance repository on a workstation, creates the VM, installs Kubernetes and ArgoCD, and hands over the instance's settings, secrets and IAM configuration. ArgoCD then deploys everything else from this (base) repository. Airlock Microgateway is the only way in: it routes to Airlock IAM and protects the administration tools, which use IAM for login.

<img src="stack.svg" width="100%" alt="Component stack: VM, Talos Linux, Kubernetes, cluster services, data, Microgateway, applications">

## Overview

```mermaid
flowchart LR
    subgraph ws["Workstation"]
        inst["Instance repository<br/>settings (sops), IAM configuration,<br/>state, backups"]
        tofu["make / OpenTofu<br/>(base repository checked out<br/>in ./salesdemo)"]
        inst --> tofu
    end

    base[("Base repository<br/>(GitHub)")]

    subgraph vm["VM: Talos Linux + Kubernetes (single node)"]
        argocd["ArgoCD"]
        mgw["Airlock Microgateway"]
        iam["Airlock IAM"]
        tools["Tools: Adminer, Headlamp,<br/>Mailpit, qr-service"]
        infra["Platform services: PureLB,<br/>cert-manager, MariaDB,<br/>Valkey, local-path"]
        argocd -- deploys --> mgw & iam & tools & infra
        mgw --> iam & tools
    end

    users(["Browser:<br/>users, administrators"])
    ext(["External services:<br/>Airlock 2FA (Futurae), PXL Vision,<br/>SMTP / SMS, Let's Encrypt"])

    tofu -- "phase 1: VM<br/>phase 2: Talos API<br/>phase 3: Kubernetes API" --> vm
    argocd -- pulls manifests --> base
    users -- "HTTPS 443<br/>(8443 Adminapp)" --> mgw
    iam --> ext
```

Two repositories:

| Repository | Content | Who changes it |
|---|---|---|
| **Base** (this one) | the installation: OpenTofu phases, Kubernetes manifests of all applications, IAM configuration template, design kit | maintained centrally, released with tags; instances pick a release (`release` file) |
| **Instance** (one per demo, from the [template](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template)) | settings (encrypted with sops/age), the instance's IAM configuration and texts, OpenTofu state, provider locks, database backups | the instance owner |

The instance repository never leaves the workstation's control: ArgoCD reads only the base repository. Instance-specific values reach the cluster through OpenTofu (ConfigMaps and Secrets, see [deployment](#deployment)).

## Runtime components

```mermaid
flowchart TB
    browser(["Browser"])

    subgraph k8s["Kubernetes"]
        lb["PureLB<br/>LoadBalancer IP"]

        subgraph gw["airlock-gateway"]
            gateway["Microgateway Gateway<br/>TLS, routing, WAF,<br/>OIDC relying party for tools"]
            mgwvk[("Valkey<br/>gateway sessions")]
            gateway --- mgwvk
        end

        subgraph iamns["iam"]
            login["IAM Loginapp<br/>/auth-login/"]
            admin["IAM Adminapp<br/>/auth-admin/"]
            db[("MariaDB<br/>users, factors, audit")]
            vk[("Valkey<br/>IAM sessions, flow state")]
            login --- db & vk
            admin --- db & vk
        end

        subgraph toolns["Tools"]
            argocd["ArgoCD<br/>/argocd/"]
            adminer["Adminer<br/>/adminer/"]
            headlamp["Headlamp<br/>/headlamp/"]
            mailpit["Mailpit<br/>/mailpit/"]
            qr["qr-service"]
        end

        certm["cert-manager<br/>gateway certificate"]
        mgwop["Microgateway operator"]
    end

    ext2fa(["Airlock 2FA<br/>(Futurae)"])
    pxl(["PXL Vision<br/>identity check"])
    smtp(["SMTP server<br/>(optional)"])
    le(["Let's Encrypt<br/>(optional)"])

    browser --> lb --> gateway
    gateway --> login & admin
    gateway -- "after IAM login<br/>(OIDC)" --> argocd & adminer & headlamp & mailpit
    gateway --> qr
    login -- emails --> mailpit
    login -. "or" .-> smtp
    login --> ext2fa & pxl
    adminer --> db
    mgwop -. configures .-> gateway
    certm -. certificate .-> gateway
    certm -.-> le
```

| Component | Role |
|---|---|
| **Airlock Microgateway** | Kubernetes Gateway API implementation and the single entry point: TLS termination (certificate from cert-manager or provided), HTTP routes to IAM and the tools, deny rules, access control. For the tools it is the OIDC relying party of IAM and propagates the identity (token exchange for ArgoCD, basic authentication for Mailpit, header for Adminer). Sessions in its own Valkey. The operator in `airlock-microgateway-system` turns the Gateway resources into the gateway deployment. |
| **Airlock IAM** | one container (StatefulSet `iam-0`) with Loginapp (login, registration, self-services, portal, recovery, OAuth 2.0 / OIDC authorization server for the tools) and Adminapp (helpdesk, user management, Config Editor). Init containers prepare the instance, copy the IAM configuration and texts and set up the database (schema, administrators, realm roles). |
| **MariaDB** | IAM database, run by the MariaDB operator, data on the local data disk. |
| **Valkey** (2×) | IAM state repository (sessions, flow state) and Microgateway session store - both in memory, no persistence. |
| **cert-manager** | cluster CA (`internal`) or Let's Encrypt (`letsencrypt`, HTTP-01 through the gateway) for the gateway certificate. |
| **PureLB** | gives the gateway's LoadBalancer Service an IP address from `lb_pool`. |
| **local-path-provisioner** | persistent volumes on the VM's second disk. |
| **ArgoCD** | deploys and keeps all applications in sync with the base repository (app-of-apps). |
| **Tools** | Adminer (database UI), Headlamp (Kubernetes UI), Mailpit (catches IAM's emails if no SMTP server is set), qr-service (QR codes for the PXL Vision check), argocd-cli (debug container). |

URLs and credentials: [usage](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template/blob/main/docs/usage.md).

## Deployment

```mermaid
flowchart TB
    subgraph ws["Workstation: make (instance repository)"]
        p1["Phase 1 - infrastructure<br/>01-infrastructure/platforms/*"]
        p2["Phase 2 - Talos<br/>02-talos"]
        p3["Phase 3 - ArgoCD<br/>03-argocd"]
        p1 -- "outputs: IPs, LB pool,<br/>installer image" --> p2 --> p3
    end

    subgraph k8s["Kubernetes"]
        cfg["ConfigMaps / Secrets<br/>project-settings, iam-config,<br/>iam-ui-customizations, licenses,<br/>passwords, keys"]
        acd["ArgoCD + app-of-apps"]
        apps["Applications in sync waves<br/>storage → CRDs → PureLB → cert-manager →<br/>Microgateway, MariaDB → gateway →<br/>Mailpit, qr-service → IAM → Adminer, Headlamp"]
        acd --> apps
        cfg -. "read by apply-config.sh<br/>while rendering" .-> apps
    end

    base[("Base repository<br/>at release")]

    p1 -- "VM, disks, network<br/>(hypervisor / cloud API)" --> vmnode["VM with Talos<br/>(maintenance mode)"]
    p2 -- "machine config,<br/>bootstrap (Talos API)" --> vmnode
    p3 -- "Kubernetes API" --> cfg & acd
    base --> acd
```

- **Phase 1** creates the VM and its surroundings on the chosen platform and publishes a small [contract](../01-infrastructure/README.md) (IP addresses, LoadBalancer pool, ...) for the next phases.
- **Phase 2** configures Talos through its API, bootstraps Kubernetes and writes `output/kubeconfig.yaml` and `output/talosconfig.yaml` into the instance directory.
- **Phase 3** writes the settings, secrets (licenses, generated passwords and keys) and the IAM configuration into the cluster, installs ArgoCD and the app-of-apps.
- **ArgoCD** renders each application from the base repository. Per-instance values (FQDN, issuer, IP addresses, ...) come from the ConfigMap `argocd/project-settings`: each application's `apply-config.sh` fills them into placeholders. A hash of the settings makes ArgoCD render again after a change.
- **IAM configuration** is not in git as seen by ArgoCD: OpenTofu puts the instance's `iam/` (configuration, texts, design kit zip) into ConfigMaps; IAM restarts when they change and copies them into its instance at start.

The OpenTofu state is stored encrypted in the instance repository - with the age key, the instance repository is all that is needed to rebuild or remove the instance ([backup](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template/blob/main/docs/backup.md)).

## IAM functional view

```mermaid
flowchart LR
    user(["End user"])
    adm(["Administrator /<br/>partner admin"])

    subgraph login["Loginapp"]
        auth["Login<br/>password + 2nd factor,<br/>passkey, username-less"]
        reg["Self-registration<br/>easy / with ID check"]
        rec["Recovery<br/>forgotten password,<br/>lost 2nd factor (points)"]
        portal["Portal + self-services<br/>factors, profile, recovery data"]
        oidc["Authorization server 'demo'<br/>OIDC for the tools"]
        lua["Lua scripts<br/>(admin lookup, realms,<br/>recovery contacts)"]
    end

    subgraph adminapp["Adminapp"]
        help["User management,<br/>helpdesk, realm administration"]
        rest["REST API"]
        ce["Config Editor"]
    end

    tools(["Tools via Microgateway:<br/>ArgoCD, Adminer,<br/>Headlamp, Mailpit"])
    fut(["Airlock 2FA<br/>(Futurae)"])
    pxl(["PXL Vision"])
    mail(["Email / SMS"])

    user --> auth & reg & rec
    auth --> portal
    adm --> auth
    portal -- "SSO ticket<br/>(Airlock 2FA or passkey)" --> help
    portal --> tools
    tools -- OIDC --> oidc
    reg & rec --> lua --> rest
    auth & portal & rec --> fut
    reg & portal & rec --> pxl
    reg & rec --> mail
```

- **Applications** (target of a login): `demo` (portal), `usernameless`, `recovery`, `adminapp-local` (Adminapp from the portal), tool applications (`argocd`, `adminer`, `headlamp`, `mailpit`), step-ups (`identity-step-up`, `config-restore-step-up`) and `adminapp` (partner administrator onboarding via an external OIDC provider, prepared but inactive). Administrator applications require Airlock 2FA or a passkey.
- **Administrators are users** in realms (`owners`, `partners`, `orphans`, `users-<company>`); realm roles and delegations define what they may do in the Adminapp. Partner administrators manage the users who named them at the self-registration.
- **Lua scripts** in the flows use the Adminapp REST API as technical administrator `selfreg-lookup` (lookup of the responsible administrator, partner realms, recovery contacts and confirmations).
- **Configuration**: one `iam-config.yaml` per instance, optional snippets for instance-specific features, server-side texts, and the design kit zip for the Loginapp UI (styling, UI texts in en/de/fr/it).

What can be demonstrated: [use cases](use-cases.md); flow details: [usage](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template/blob/main/docs/usage.md).

## Network and platforms

```mermaid
flowchart LR
    ws(["Workstation"])
    br(["Browsers"])

    subgraph vm["VM"]
        talos["Talos API :50000<br/>Kubernetes API :6443"]
        lbip["Gateway LoadBalancer IP<br/>:80 :443 :8443"]
    end

    ws -- "endpoint_ip<br/>(admin IPs only on Azure)" --> talos
    br -- "demo_fqdn → gateway IP" --> lbip
```

| | local (e.g. VMware Workstation) | kvm | azure |
|---|---|---|---|
| VM created by | you, boots the Talos ISO | OpenTofu on the KVM host (libvirt over ssh) | OpenTofu (resource group, VNet, NSG, storage, VM) |
| Talos | boots the ISO, installed to disk in phase 2 | boots the disk image, installer run in phase 2 (`/dev/vda`) | boots the disk image (no install) |
| Node / API address | fixed IP (DHCP reservation) | fixed IP (DHCP reservation) | public admin IP, NATed to the private NIC address |
| Gateway address | first address of `lb_pool` in the VM's subnet | first address of `lb_pool` | second private IP of the NIC (PureLB), NATed from a second public IP with DNS label |
| Name resolution of `demo_fqdn` | hosts file / local DNS | hosts file / DNS | public DNS (A or CNAME record) |
| Access restriction | network | network | NSG: Talos/Kubernetes API and 8443 only from `vm_admin_ips` |
| Certificate | `internal` (or `provided`) | `internal` (or `provided`) | `letsencrypt` recommended |

Port 8443 leads to the same Adminapp as `/auth-admin/` on 443, but only from `vm_admin_ips` (Microgateway access control policy). Platform requirements and steps: `docs/platform-<platform>.md` in the instance template; adding a platform: [01-infrastructure](../01-infrastructure/README.md).
