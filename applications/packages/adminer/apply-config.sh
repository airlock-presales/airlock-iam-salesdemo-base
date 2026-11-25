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
# automatic login: user header name (Microgateway) and the corresponding $_SERVER key (PHP)
auth_header="$(yq '.tools.adminer.auth_header' ${settings})"
auth_key="HTTP_$(echo "${auth_header}" | tr 'a-z-' 'A-Z_')"
sed -i -e "s|@@FQDN@@|${fqdn}|g" -e "s|@@AUTH_HEADER@@|${auth_header}|g" -e "s|@@AUTH_KEY@@|${auth_key}|g" adminer.yaml gateway.yaml
