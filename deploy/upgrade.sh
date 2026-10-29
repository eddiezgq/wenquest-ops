#!/usr/bin/env bash
# Upgrade: back up first, then pull the new hub image and restart.
#   ./upgrade.sh [image tag, default latest] [--company new-company.yaml]
# A new company manifest is checked first (nothing changes when it has errors); new warehouses, departments and
# addresses are then created in ERPNext. Company name, currency and time zone are fixed at installation.
. "$(dirname "$0")/lib.sh"
tag=latest COMPANY=""
while [ $# -gt 0 ]; do
    case "$1" in
        --company) COMPANY=$(abspath "$2"); shift 2 ;;
        -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
        *) tag=$1; shift ;;
    esac
done
[ -z "$COMPANY" ] || [ -f "$COMPANY" ] || die "no such company manifest: $COMPANY"
"$WD/backup.sh" >/dev/null && log "Backed up before upgrading"
cur=$(envval WQO_HUB_IMAGE)                # keep the registry the installation pulls from (a mirror in China)
envset WQO_HUB_IMAGE "${cur%/wenquest-ops-hub:*}/wenquest-ops-hub:$tag"
[ -n "$cur" ] || envset WQO_HUB_IMAGE "ghcr.io/eddiezgq/wenquest-ops-hub:$tag"
[ "${WQO_NO_PULL:-0}" = 1 ] || dc pull --quiet hub
[ -z "$COMPANY" ] || company_put "$COMPANY"
dc up -d
dc restart hub
[ -z "$COMPANY" ] || dc exec -T hub python -m wqops.erp_setup apply /company/company.yaml
log "Upgrade done ($tag)"
"$WD/status.sh"
