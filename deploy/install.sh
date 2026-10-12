#!/usr/bin/env bash
# WenQuest Ops - first installation on one server (docs/ops/README.md). Safe to run again: finished steps are skipped.
#
#   ./install.sh --company company.yaml --domain ops.example.com --email it@example.com
#
#   --company FILE      the company manifest (python -m wqops.company template / import); required the first time
#   --domain NAME       the WenQuest Ops address; ERPNext gets erp.<NAME> unless --erp-domain is given
#   --erp-domain NAME
#   --email ADDRESS     contact for Let's Encrypt certificates (the domains must point at this server)
#   --tls-internal      self-signed certificate instead (intranet, testing)
#   --image TAG         hub image tag (default latest); --no-pull uses images already on this machine
#   --registry-token T  token for pulling the private hub image
# The first owner in the manifest gets a password: from WQO_OWNER_PASSWORD, or asked for when run in a terminal.
. "$(dirname "$0")/lib.sh"

COMPANY="" DOMAIN="" ERP_DOMAIN="" EMAIL="" TLS_INTERNAL=0 TAG=latest PULL=1 REG_TOKEN="${WQO_REGISTRY_TOKEN:-}"
while [ $# -gt 0 ]; do
    case "$1" in
        --company) COMPANY=$(abspath "$2"); shift 2 ;;
        --domain) DOMAIN=$2; shift 2 ;;
        --erp-domain) ERP_DOMAIN=$2; shift 2 ;;
        --email) EMAIL=$2; shift 2 ;;
        --tls-internal) TLS_INTERNAL=1; shift ;;
        --image) TAG=$2; shift 2 ;;
        --no-pull) PULL=0; shift ;;
        --registry-token) REG_TOKEN=$2; shift 2 ;;
        -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

# ---------------------------------------------------------------- 1 checks
log "Checking this server..."
command -v docker >/dev/null || die "Docker is missing. On Ubuntu: curl -fsSL https://get.docker.com | sh"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is missing"
command -v curl >/dev/null || die "curl is missing"
mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)
[ "$mem_gb" -ge "${WQO_MIN_MEM_GB:-7}" ] || die "${mem_gb} GB of memory; at least 8 GB is needed (16 GB recommended)"
disk_gb=$(df -Pk "$WD" | awk 'NR==2 {printf "%d", $4/1024/1024}')
[ "$disk_gb" -ge "${WQO_MIN_DISK_GB:-40}" ] || die "${disk_gb} GB of free disk; at least 40 GB is needed"
[ -z "$COMPANY" ] || [ -f "$COMPANY" ] || die "no such company manifest: $COMPANY"
[ -n "$COMPANY" ] || [ -f company/company.yaml ] || die "give --company company.yaml (see docs/ops/README.md)"

# ---------------------------------------------------------------- 2 settings and secrets (generated once)
[ -n "$DOMAIN" ] || DOMAIN=$(envval WQO_DOMAIN)
[ -n "$DOMAIN" ] || die "give --domain"
[ -n "$ERP_DOMAIN" ] || ERP_DOMAIN=$(envval WQO_ERP_DOMAIN)
[ -n "$ERP_DOMAIN" ] || ERP_DOMAIN="erp.$DOMAIN"
envset WQO_DOMAIN "$DOMAIN"
envset WQO_ERP_DOMAIN "$ERP_DOMAIN"
if [ "$TLS_INTERNAL" = 1 ]; then envset WQO_TLS internal
elif [ -n "$EMAIL" ]; then envset WQO_TLS "$EMAIL"
elif [ -z "$(envval WQO_TLS)" ]; then die "give --email (Let's Encrypt) or --tls-internal"
fi
envset WQO_HUB_IMAGE "${WQO_HUB_IMAGE:-ghcr.io/eddiezgq/wenquest-ops-hub:$TAG}"
for k in WQO_DB_PASSWORD WQO_SECRET WQO_ERP_SSO_SECRET ERP_DB_ROOT_PASSWORD; do
    [ -n "$(envval "$k")" ] || envset "$k" "$(rand 32)"
done
[ -n "$(envval ERP_ADMIN_PASSWORD)" ] || envset ERP_ADMIN_PASSWORD "$(rand 20)"

# ---------------------------------------------------------------- 3 images and the company manifest
if [ "$PULL" = 1 ]; then
    [ -z "$REG_TOKEN" ] || printf '%s' "$REG_TOKEN" | docker login ghcr.io -u "${WQO_REGISTRY_USER:-wqo}" --password-stdin >/dev/null
    log "Pulling images (5-10 minutes the first time)..."
    dc pull --quiet
fi
if [ -n "$COMPANY" ]; then log "Checking the company manifest..."; company_put "$COMPANY"; fi
log "Domains: $DOMAIN and $ERP_DOMAIN; certificate: $(envval WQO_TLS)"

# ---------------------------------------------------------------- 4 ERPNext
log "Starting ERPNext..."
dc up -d erp-db erp-redis-cache erp-redis-queue
dc up -d erp-configurator
dc up -d erp-backend erp-websocket erp-queue-short erp-queue-long erp-scheduler erp-frontend
for _ in $(seq 1 60); do dc exec -T erp-backend true 2>/dev/null && break; sleep 3; done
if ! dc exec -T erp-backend test -d sites/frontend; then
    log "Creating the ERPNext site (3-5 minutes)..."
    dc exec -T erp-backend bench new-site --mariadb-user-host-login-scope='%' \
        --admin-password="$(envval ERP_ADMIN_PASSWORD)" \
        --db-root-username=root --db-root-password="$(envval ERP_DB_ROOT_PASSWORD)" \
        --install-app erpnext --set-default frontend
fi
setup=$(bench_exec frappe.is_setup_complete 2>/dev/null | tail -n 1 || true)
if [ "$setup" != "true" ] && [ "$setup" != "True" ] && [ "$setup" != "1" ]; then
    log "Running the ERPNext setup wizard for the company..."
    wiz=$(dc run --rm --no-deps -T hub python -m wqops.erp_setup wizard-args /company/company.yaml)
    bench_exec frappe.desk.page.setup_wizard.setup_wizard.initialize_system_settings_and_user \
        --kwargs "$(printf '%s\n' "$wiz" | sed -n 1p)"
    bench_exec frappe.desk.page.setup_wizard.setup_wizard.setup_complete --kwargs "$(printf '%s\n' "$wiz" | sed -n 2p)"
fi
dc exec -T erp-backend bench --site frontend set-config host_name "https://$ERP_DOMAIN" >/dev/null
if [ -z "$(envval WQO_ERP_API_KEY)" ]; then
    log "Creating the API key the hub uses to talk to ERPNext..."
    keys=$(bench_exec frappe.core.doctype.user.user.generate_keys --args "['Administrator']" | tail -n 1)
    envset WQO_ERP_API_KEY "$(printf '%s' "$keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_key"])')"
    envset WQO_ERP_API_SECRET "$(printf '%s' "$keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_secret"])')"
fi

# ---------------------------------------------------------------- 5 hub, entry point, the business in ERPNext
log "Starting the hub..."
dc up -d db hub caddy
log "Creating warehouses, departments and addresses in ERPNext..."
ok=0
for i in 1 2 3 4 5; do
    if dc exec -T hub python -m wqops.erp_setup apply /company/company.yaml; then ok=1; break; fi
    log "not yet, retrying in 20 s ($i)..."; sleep 20
done
[ "$ok" = 1 ] || die "could not create the business in ERPNext (see above)"
for _ in $(seq 1 60); do
    dc exec -T hub python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/api/health', timeout=5)" \
        >/dev/null 2>&1 && break
    sleep 5
done

# ---------------------------------------------------------------- 6 the first owner's password
has_pw=$(dc exec -T hub python -c "
import os
from wqops.hub import db, accounts
c = db.connect(os.environ['WQO_DB'])
print(int(bool(c.execute(\"select 1 from users where 'owner' = any(roles) and password_hash is not null\").fetchone())))
" 2>/dev/null | tail -n 1 || echo 0)
if [ "$has_pw" != 1 ]; then
    pw="${WQO_OWNER_PASSWORD:-}"
    if [ -z "$pw" ] && [ -t 0 ]; then
        read -r -s -p "Password for the owner in company.yaml (10+ characters, letters and digits): " pw; echo
    fi
    if [ -n "$pw" ]; then
        printf '%s\n' "$pw" | dc exec -T hub python -m wqops.hub.accounts set-owner-password || die "could not set the owner password"
    else
        log "No owner password set yet. Set it with:"
        log "  echo 'the password' | docker compose -p wqo exec -T hub python -m wqops.hub.accounts set-owner-password"
    fi
fi

"$WD/backup.sh" >/dev/null && log "First backup done (backups/)"
envset WQO_INSTALLED "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Installed:"
log "  WenQuest Ops  https://$DOMAIN (sign in as the owner in company.yaml)"
log "  ERPNext       https://$ERP_DOMAIN (user Administrator; password is ERP_ADMIN_PASSWORD in $WD/.env)"
log "  Health check  https://$DOMAIN/api/health"
"$WD/status.sh"
