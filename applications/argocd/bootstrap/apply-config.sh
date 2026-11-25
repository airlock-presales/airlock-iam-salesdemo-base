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

# set repository and release of the instance in all applications; the hash of the project settings
# (plugin env SETTINGS_HASH) changes the applications when a setting changes, so ArgoCD renders their
# manifests again (it caches them per git revision and application source)
set -euo pipefail

settings=/home/argocd/project-settings/settings
repo="$(yq '.kubernetes.argocd.repository.url' ${settings})"
release="$(yq '.demo.release' ${settings})"
# hash set by OpenTofu (plugin env of this application), the file matches it (checked above)
hash="${ARGOCD_ENV_SETTINGS_HASH:-$(sha256sum ${settings} | cut -c1-16)}"
sed -i -e "s|@@REPO@@|${repo}|g" -e "s|@@RELEASE@@|${release}|g" -e "s|@@SETTINGS_HASH@@|${hash}|g" *.yaml
