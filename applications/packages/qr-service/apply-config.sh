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

fqdn="$(yq '.demo.fqdn' /home/argocd/project-settings/settings)"
sed -i -e "s|@@FQDN@@|${fqdn}|g" qr-service.yaml
