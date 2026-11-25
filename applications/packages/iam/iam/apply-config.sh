#! /bin/bash
# Project settings are mounted from a configmap and updated with a delay: wait until they match the
# hash of this rendering (set by OpenTofu, passed on by the bootstrap application) - otherwise old
# values would be rendered and cached under the new hash
_settings_file=/home/argocd/project-settings/settings
if [[ -n "${ARGOCD_ENV_SETTINGS_HASH:-}" ]]; then
    for _i in $(seq 1 30); do
        [[ "$(sha256sum "${_settings_file}" | cut -c1-16)" == "${ARGOCD_ENV_SETTINGS_HASH}" ]] && break
        if [[ ${_i} -eq 30 ]]; then
            echo "project settings not yet updated (expected hash ${ARGOCD_ENV_SETTINGS_HASH})" >&2
            exit 1
        fi
        sleep 2
    done
fi

set -euo pipefail

settings=/home/argocd/project-settings/settings
fqdn="$(yq '.demo.fqdn' ${settings})"
tz="$(yq '.vm.timezone' ${settings})"
config_sync="$(yq '.airlock.iam.config_sync' ${settings})"
# users allowed to restore the deployed configuration (portal): regex for the access condition of the
# self-service flow config-restore, e.g. ^(admin|j[.]doe)$; empty list: all (.*). Usernames contain only
# letters, digits and . _ @ + - (validated by OpenTofu); "." and "+" are escaped as [.] and [+]
restore_users_pattern="$(yq '.airlock.iam.config_restore_users | map(sub("\\.", "[.]") | sub("\\+", "[+]")) | join("|")' ${settings})"
if [[ -z "${restore_users_pattern}" ]]; then
    restore_users_pattern='.*'
else
    restore_users_pattern="^(${restore_users_pattern})\$"
fi
# Airlock 2FA recovery instructions in the portal (true/false)
airlock2fa_recovery_info="$(yq '.airlock.iam.airlock2fa_recovery_info // false' ${settings})"
config_hash="$(yq '.airlock.iam.config_hash' ${settings})"
sed -i -e "s|@@FQDN@@|${fqdn}|g" gateway/httproutes.yaml gateway/httproutes-admin.yaml
sed -i -e "s|@@FQDN@@|${fqdn}|g" -e "s|@@TIMEZONE@@|${tz}|g" -e "s|@@IAM_CONFIG_SYNC@@|${config_sync}|g" \
    -e "s#@@CONFIG_RESTORE_USERS_PATTERN@@#${restore_users_pattern}#g" \
    -e "s|@@AIRLOCK2FA_RECOVERY_INFO@@|${airlock2fa_recovery_info}|g" \
    -e "s|@@IAM_CONFIG_HASH@@|${config_hash}|g" statefulset.yaml

# local administrator (port 8443): IP allow-list from vm_admin_ips (single addresses as /32 or /128);
# no restriction if vm_admin_ips is empty
cidrs=()
for ip in $(yq '.vm.admin_ips[]' ${settings}); do
    if [[ "${ip}" == */* ]]; then
        cidrs+=("${ip}")
    elif [[ "${ip}" == *:* ]]; then
        cidrs+=("${ip}/128")
    else
        cidrs+=("${ip}/32")
    fi
done
if [[ ${#cidrs[@]} -gt 0 ]]; then
    list="$(printf '"%s",' "${cidrs[@]}")"
    yq -i ".spec.policies[0].requestConditions.remoteIP.cidrRanges = [${list%,}]" gateway/admin-ip-allowlist.yaml
else
    yq -i 'del(.resources[] | select(. == "gateway/admin-ip-allowlist.yaml"))' kustomization.yaml
fi
