# shellcheck shell=bash
# Shared helpers for the WenQuest Ops deployment scripts. Sourced, never run directly.
# The install directory is the directory holding these scripts (e.g. /opt/wenquest-ops).
set -euo pipefail

WD="${WQO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
CALLER_PWD=$PWD
abspath() { case "$1" in /*) printf '%s' "$1" ;; *) printf '%s/%s' "$CALLER_PWD" "$1" ;; esac; }
cd "$WD"
mkdir -p backups company

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

envval() {   # read one key from .env without sourcing it
    local line
    line=$(grep -E "^$1=" "${2:-.env}" 2>/dev/null | tail -n 1 || true)
    printf '%s' "${line#*=}"
}

envset() {
    touch .env && chmod 600 .env
    local v=${2//|/\\|}
    if grep -qE "^$1=" .env; then
        sed -i "s|^$1=.*|$1=$v|" .env
    else
        printf '%s=%s\n' "$1" "$2" >> .env
    fi
}

rand() { tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "${1:-24}" || true; }

dc() { docker compose -p wqo --env-file .env -f docker-compose.yml "$@"; }

# Run a Python function inside ERPNext (bench execute) and print its return value
bench_exec() { dc exec -T erp-backend bench --site frontend execute "$@"; }

# Validate a company manifest with the hub image, then install it as company/company.yaml
company_put() {
    cp "$1" company/company.new.yaml && chmod 644 company/company.new.yaml
    if ! dc run --rm --no-deps -T hub python -m wqops.company check /company/company.new.yaml; then
        rm -f company/company.new.yaml
        die "the company manifest has errors (listed above); fix them and run again"
    fi
    mv company/company.new.yaml company/company.yaml
}
