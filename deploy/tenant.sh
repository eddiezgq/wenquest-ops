#!/usr/bin/env bash
# Pilot companies on one server (ADR-0025). Run from the demo installation (e.g. /opt/wenquest/qms); each pilot company
# is its own installation next to it in <WQO_TENANTS_DIR, default ../qms-tenants>/<id>, compose project qms-<id>,
# reached as <id>.<demo domain> and <id>.<demo ERPNext domain>.
#
#   ./tenant.sh new <id> --name "Company" --contact "Owner name" --email owner@company.com [--lang zh|en]
#                        [--result FILE]     where the new owner's sign-in goes (JSON, mode 600); else printed
#   ./tenant.sh demo <id> --company FILE     a second demo company next to the demo (ADR-0026 26f: the sewing machine
#                                            factory): installs it, loads its demo data, opens trial accounts there
#                                            and resets it every night like the demo (ADR-0027)
#   ./tenant.sh list
#   ./tenant.sh stop <id> | start <id>       stop keeps every record; start brings it back
#   ./tenant.sh upgrade-all [tag]            the demo's upgrade for every pilot company, one after another
#
# The settings come from the demo installation's .env: China or not, the image registry, the AI key.
# A new company is refused when the server has less than WQO_TENANT_MIN_FREE_MB (default 1536) of memory free.
# WQO_HUB_IMAGE, when set, overrides the demo's hub image (CI uses an image built on the spot).
. "$(dirname "$0")/lib.sh"

BASE=$WD
TENANTS=${WQO_TENANTS_DIR:-$(dirname "$BASE")/qms-tenants}
RESERVED=" demo www api admin erp mail qms test staging "
cmd=${1:-}; shift || true

valid_id() { [[ "$1" =~ ^[a-z][a-z0-9-]{2,19}$ ]] && [[ "$1" != *- ]] && [[ "$RESERVED" != *" $1 "* ]]; }
tdir() { printf '%s/%s' "$TENANTS" "$1"; }
in_tenant() { local d; d=$(tdir "$1"); [ -f "$d/.env" ] || die "no pilot company $1"; (cd "$d" && WQO_DIR="$d" "${@:2}"); }

case "$cmd" in
new)
    id=${1:-}; shift || true
    NAME="" CONTACT="" EMAIL="" LANG_="" RESULT=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --name) NAME=$2; shift 2 ;;
            --contact) CONTACT=$2; shift 2 ;;
            --email) EMAIL=$2; shift 2 ;;
            --lang) LANG_=$2; shift 2 ;;
            --result) RESULT=$(abspath "$2"); shift 2 ;;
            *) die "unknown option: $1 (see --help)" ;;
        esac
    done
    valid_id "$id" || die "the id is 3-20 lower-case letters, digits or -, starting with a letter, and not one of:$RESERVED"
    [ -n "$NAME" ] && [ -n "$CONTACT" ] && [[ "$EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] \
        || die "give --name, --contact and a valid --email"
    [ -f "$BASE/.env" ] && [ -n "$(envval WQO_INSTALLED "$BASE/.env")" ] || die "run this from the demo installation"
    d=$(tdir "$id")
    [ ! -e "$d/.env" ] || die "pilot company $id exists already ($d)"
    free_mb=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
    [ "$free_mb" -ge "${WQO_TENANT_MIN_FREE_MB:-1536}" ] \
        || die "only ${free_mb} MB of memory free; a pilot company needs about 900 MB plus room. Upgrade the server first"
    cn=$(envval WQO_DEPLOYMENT "$BASE/.env")
    [ -n "$LANG_" ] || { [ "$cn" = cn ] && LANG_=zh || LANG_=en; }

    log "Preparing $d ..."
    mkdir -p "$d/company"
    for f in "$BASE"/*.sh "$BASE"/docker-compose*.yml "$BASE"/Caddyfile*; do cp "$f" "$d/"; done
    touch "$d/.env" && chmod 600 "$d/.env"
    for k in WQO_DEPLOYMENT WQO_MIRROR WQO_HUB_IMAGE WQO_ERP_IMAGE WQO_CADDY_IMAGE WQO_DB_IMAGE WQO_MARIADB_IMAGE \
             WQO_REDIS_IMAGE WQO_DEEPSEEK_API_KEY WQO_ANTHROPIC_API_KEY WQO_AI_PROVIDER; do
        v=$(envval "$k" "$BASE/.env"); [ -z "$v" ] || printf '%s=%s\n' "$k" "$v" >> "$d/.env"
    done
    printf 'WQO_EDGE_NAME=qms-%s-edge\nWQO_TENANT=%s\nWQO_TENANT_CREATED=%s\n' "$id" "$id" "$(date -u +%FT%TZ)" >> "$d/.env"
    # ADR-0025 25d: 200 AI runs a day; the owner changes the first password; problems people report go by email once a
    # day to whoever runs the WenQuest platform on this server, through its mail settings (../.env), when it has them
    printf 'WQO_AI_DAILY=%s\nWQO_MUST_CHANGE=1\n' "${WQO_TENANT_AI_DAILY:-200}" >> "$d/.env"
    wq="$(dirname "$BASE")/.env"
    if [ -r "$wq" ]; then
        for pair in SMTP_HOST:WQO_SMTP_HOST SMTP_PORT:WQO_SMTP_PORT SMTP_SECURE:WQO_SMTP_SECURE SMTP_USER:WQO_SMTP_USER \
                    SMTP_PASSWORD:WQO_SMTP_PASSWORD MOODLE_NOREPLY_EMAIL:WQO_SMTP_SENDER; do
            v=$(envval "${pair%%:*}" "$wq"); [ -z "$v" ] || printf '%s=%s\n' "${pair##*:}" "$v" >> "$d/.env"
        done
        to=$(envval WQ_ADMIN_EMAIL "$wq"); [ -n "$to" ] || to=$(envval MOODLE_ADMIN_EMAIL "$wq")
        [ -z "$to" ] || printf 'WQO_FEEDBACK_TO=%s\n' "$to" >> "$d/.env"
    fi
    python3 - "$d/company/start.yaml" "$id" "$NAME" "$CONTACT" "${EMAIL,,}" "$LANG_" <<'PY'
import json, re, sys
out, cid, name, contact, email, lang = sys.argv[1:]
zh = lang == "zh"
abbr = re.sub(r"[^A-Z]", "", cid.upper())[:5] or "CO"
c = {"name": name, "abbr": abbr, "fiscal_year_start": "01-01", "language": lang}
c |= ({"country": "China", "currency": "CNY", "timezone": "Asia/Shanghai", "date_format": "yyyy-mm-dd",
       "units": {"weight": "kg", "length": "cm"}} if zh else
      {"country": "United States", "currency": "USD", "timezone": "America/New_York", "date_format": "mm-dd-yyyy",
       "units": {"weight": "lb", "length": "in"}})
site = "总部" if zh else "Head Office"
m = {"version": 1, "demo": False, "company": c,
     "sites": [{"id": "hq", "name": site, "kind": "office"}],          # the address is added later in the manifest
     "warehouses": [{"id": "main", "name": "主仓" if zh else "Main Stock", "site": "hq", "kind": "stores"}],
     "departments": [{"id": "leadership", "name": "管理层" if zh else "Leadership"}],
     "people": [{"name": contact, "email": email, "roles": ["owner"], "department": "leadership"}],
     "modules": ["core", "hub", "ai", "quality"]}
# JSON is valid YAML, and keeps any name exactly as typed
open(out, "w", encoding="utf-8").write(json.dumps(m, ensure_ascii=False, indent=1))
PY
    pw="$(rand 6)-$(rand 6)-$(tr -dc '0-9' < /dev/urandom | head -c 2 || true)"
    dom="$id.$(envval WQO_DOMAIN "$BASE/.env")" erp="$id.$(envval WQO_ERP_DOMAIN "$BASE/.env")"
    img=${WQO_HUB_IMAGE:-$(envval WQO_HUB_IMAGE "$BASE/.env")}; tag=${img##*:}   # the demo's hub image unless given
    small=(); [[ ":$(envval WQO_COMPOSE_FILES "$BASE/.env"):" != *:docker-compose.small.yml:* ]] || small=(--small)
    china=(); [ "$cn" != cn ] || china=(--china)
    log "Installing $NAME as $dom (10-15 minutes) ..."
    exec 9>/tmp/wenquest-deploy.lock
    flock -w 1500 9 || die "another deployment holds the lock; try again later"
    (cd "$d" && WQO_DIR="$d" WQO_HUB_IMAGE="$img" WQO_OWNER_PASSWORD="$pw" WQO_MIN_DISK_GB="${WQO_MIN_DISK_GB:-15}" ./install.sh \
        --company company/start.yaml --domain "$dom" --erp-domain "$erp" --edge "${small[@]}" "${china[@]}" \
        --project "qms-$id" --image "${tag:-latest}" --no-pull) || die "the installation of $id stopped (see above); run the same command again"
    flock -u 9
    # a daily backup, a few minutes after the demo's (04:10), one minute apart per company
    n=$(find "$TENANTS" -mindepth 1 -maxdepth 1 -type d | wc -l)
    line="$((15 + n % 40)) 4 * * * cd $d && WQO_KEEP=7 ./backup.sh >> $d/backups/cron.log 2>&1"
    if command -v crontab >/dev/null; then
        { crontab -l 2>/dev/null | grep -v "$d && WQO_KEEP=7 ./backup.sh" || true; echo "$line"; } | crontab -
    else log "note: no crontab here; add the daily backup yourself: $line"; fi
    res=$(python3 -c 'import json,sys; print(json.dumps(dict(zip(["id","name","email","password","url","erp_url"], sys.argv[1:])), ensure_ascii=False))' \
        "$id" "$NAME" "${EMAIL,,}" "$pw" "https://$dom" "https://$erp")
    if [ -n "$RESULT" ]; then (umask 077; printf '%s\n' "$res" > "$RESULT"); log "Sign-in written to $RESULT"
    else printf '%s\n' "$res"; fi
    log "Pilot company $id is ready: https://$dom"
    ;;
demo)
    id=${1:-}; shift || true
    COMPANY=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --company) COMPANY=$(abspath "$2"); shift 2 ;;
            *) die "unknown option: $1 (see --help)" ;;
        esac
    done
    valid_id "$id" || die "the id is 3-20 lower-case letters, digits or -, starting with a letter, and not one of:$RESERVED"
    [ -f "$COMPANY" ] || die "give --company, the demo company's manifest"
    grep -q '^demo: true' "$COMPANY" || die "$COMPANY is not a demo company (demo: true)"
    [ -f "$BASE/.env" ] && [ -n "$(envval WQO_INSTALLED "$BASE/.env")" ] || die "run this from the demo installation"
    d=$(tdir "$id")
    if [ ! -f "$d/.env" ] || [ -z "$(envval WQO_INSTALLED "$d/.env")" ]; then
        free_mb=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
        [ "$free_mb" -ge "${WQO_TENANT_MIN_FREE_MB:-1536}" ] \
            || die "only ${free_mb} MB of memory free; a demo company needs about 900 MB plus room. Upgrade the server first"
        log "Preparing $d ..."
        mkdir -p "$d/company"
        for f in "$BASE"/*.sh "$BASE"/docker-compose*.yml "$BASE"/Caddyfile*; do cp "$f" "$d/"; done
        cp "$COMPANY" "$d/company/demo.yaml"
        if [ ! -f "$d/.env" ]; then
            touch "$d/.env" && chmod 600 "$d/.env"
            for k in WQO_DEPLOYMENT WQO_MIRROR WQO_HUB_IMAGE WQO_ERP_IMAGE WQO_CADDY_IMAGE WQO_DB_IMAGE WQO_MARIADB_IMAGE \
                     WQO_REDIS_IMAGE WQO_DEEPSEEK_API_KEY WQO_ANTHROPIC_API_KEY WQO_AI_PROVIDER WQO_AI_DAILY; do
                v=$(envval "$k" "$BASE/.env"); [ -z "$v" ] || printf '%s=%s\n' "$k" "$v" >> "$d/.env"
            done
            # trial accounts here too (ADR-0027), as engineering and quality so a visitor can walk a design change
            printf 'WQO_EDGE_NAME=qms-%s-edge\nWQO_TENANT=%s\nWQO_DEMO_TRIAL=1\nWQO_TRIAL_ROLES=quality,engineering\n' \
                "$id" "$id" >> "$d/.env"
        fi
        cn=$(envval WQO_DEPLOYMENT "$BASE/.env")
        dom="$id.$(envval WQO_DOMAIN "$BASE/.env")" erp="$id.$(envval WQO_ERP_DOMAIN "$BASE/.env")"
        img=${WQO_HUB_IMAGE:-$(envval WQO_HUB_IMAGE "$BASE/.env")}; tag=${img##*:}
        small=(); [[ ":$(envval WQO_COMPOSE_FILES "$BASE/.env"):" != *:docker-compose.small.yml:* ]] || small=(--small)
        china=(); [ "$cn" != cn ] || china=(--china)
        log "Installing the demo company $id as $dom (10-15 minutes) ..."
        exec 9>/tmp/wenquest-deploy.lock
        flock -w 1500 9 || die "another deployment holds the lock; try again later"
        # nobody signs in as the demo's owner: visitors come in with trial accounts
        (cd "$d" && WQO_DIR="$d" WQO_HUB_IMAGE="$img" WQO_OWNER_PASSWORD="$(rand 16)-$(rand 4)-7" \
            WQO_MIN_DISK_GB="${WQO_MIN_DISK_GB:-15}" ./install.sh --company company/demo.yaml --domain "$dom" \
            --erp-domain "$erp" --edge "${small[@]}" "${china[@]}" --project "qms-$id" --image "${tag:-latest}" --no-pull) \
            || die "the installation of $id stopped (see above); run the same command again"
        flock -u 9
    fi
    if [ ! -f "$d/.demo-loaded" ]; then
        log "Loading the demo data of $id (several minutes) ..."
        (cd "$d" && WQO_DIR="$d" bash -c '. ./lib.sh; dc exec -T hub python -m wqops.demo.load') > "$d/demo.log" 2>&1 \
            || { tail -n 30 "$d/demo.log"; die "the demo data of $id was not loaded (see $d/demo.log)"; }
        touch "$d/.demo-loaded"
        (cd "$d" && WQO_DIR="$d" ./demo-reset.sh snapshot) || log "WARNING: no clean snapshot of $id yet; the first night takes it"
    fi
    if command -v crontab >/dev/null; then        # every night after the demo's reset (04:40)
        line="10 5 * * * cd $d && grep -q ^WQO_DEMO_TRIAL=1 .env && ./demo-reset.sh >> $d/backups/demo-reset.log 2>&1"
        { crontab -l 2>/dev/null | grep -v "$d && grep -q ^WQO_DEMO_TRIAL" || true; echo "$line"; } | crontab -
    fi
    log "Demo company $id is ready: https://$(envval WQO_DOMAIN "$d/.env")"
    ;;
list)
    [ -d "$TENANTS" ] || { log "no pilot companies yet"; exit 0; }
    for d in "$TENANTS"/*/; do
        [ -f "$d.env" ] || continue
        id=$(basename "$d")
        up=$(docker ps --filter "name=^qms-$id-edge$" --format '{{.Status}}' | head -n 1)
        printf '%-20s %-45s %s\n' "$id" "https://$(envval WQO_DOMAIN "$d.env")" "${up:-stopped}"
    done
    free_mb=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
    log "memory free: ${free_mb} MB"
    ;;
stop|start)
    id=${1:-}; valid_id "$id" || die "give the pilot company's id"
    if [ "$cmd" = stop ]; then in_tenant "$id" bash -c '. ./lib.sh; dc stop'; log "$id stopped; records kept"
    else in_tenant "$id" bash -c '. ./lib.sh; dc up -d'; log "$id started"; fi
    ;;
upgrade-all)
    [ -d "$TENANTS" ] || exit 0
    for d in "$TENANTS"/*/; do
        [ -f "$d.env" ] || continue
        id=$(basename "$d")
        for f in "$BASE"/*.sh "$BASE"/docker-compose*.yml "$BASE"/Caddyfile*; do cp "$f" "$d"; done
        if docker ps --filter "name=^qms-$id-edge$" --format x | grep -q x; then
            log "Upgrading $id ..."
            (cd "$d" && WQO_DIR="$d" WQO_NO_PULL=1 ./upgrade.sh "${1:-latest}") || log "WARNING: upgrading $id failed"
        else log "$id is stopped; its files are updated, it upgrades when started"; fi
    done
    ;;
-h|--help|"") sed -n '2,16p' "$0" ;;
*) die "unknown command: $cmd (see --help)" ;;
esac
