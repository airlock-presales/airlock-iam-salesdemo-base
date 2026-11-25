#!/bin/bash
#
# Phase 1 (Azure), data source "external": is the DNS label of the demo public IP available?
# Arguments: <subscription id> <location> <resource group> <public IP name> <dns label>
# Output (stdout): JSON object for OpenTofu; exit code 1 with a message on stderr if the label is taken.
# Runs during plan, so 'apply-1' fails before anything is created.

set -euo pipefail

subscription="$1" location="$2" rg="$3" ip="$4" label="$5"

command -v az >/dev/null || { echo "Azure CLI (az) not found" >&2; exit 1; }

# the label already belongs to the demo public IP of this instance (later runs): nothing to check
current="$(az network public-ip show --subscription "${subscription}" -g "${rg}" -n "${ip}" \
  --query dnsSettings.domainNameLabel -o tsv 2>/dev/null || true)"
if [[ "${current}" == "${label}" ]]; then
  echo '{"available": "own"}'
  exit 0
fi

available="$(az rest --method get \
  --url "https://management.azure.com/subscriptions/${subscription}/providers/Microsoft.Network/locations/${location}/CheckDnsNameAvailability?domainNameLabel=${label}&api-version=2024-05-01" \
  --query available -o tsv)" || { echo "DNS label check failed (az login?)" >&2; exit 1; }

if [[ "${available}" != "true" ]]; then
  echo "DNS name ${label}.${location}.cloudapp.azure.com is already taken (unique per Azure region) -" \
       "set another platform_azure.dns_label (default airlock-<demo_name>), or \"\" for none" >&2
  exit 1
fi
echo '{"available": "true"}'
