#!/usr/bin/env bash
# A demo company installed again from nothing when its demo data changed (WenQuest round 132). Released parts and BOMs
# cannot change quietly, so new demo data means a new start; the people who had a way in keep it. Run from the demo
# company's installation (tenant.sh does, around its install and load; CI does it on its own installation):
#   ./demo-reinstall.sh out   keep the trial accounts and the owner's password hash in backups/reinstall/, then stop
#                             the company and delete its containers and data (ERPNext, database, files)
#   ./demo-reinstall.sh in    after install.sh and the demo load: put the trial accounts and the owner's password back
# A reinstall that stopped half way keeps what "out" kept; running "out" again does not read it again.
. "$(dirname "$0")/lib.sh"

keep="$WD/backups/reinstall"
case "${1:-}" in
out)
    mkdir -p "$keep" && chmod 700 "$keep"
    if [ ! -f "$keep/owner.json" ]; then
        dc exec -T hub python -m wqops.hub.trial export > "$keep/trial.json.tmp" \
            || die "could not read the trial accounts; nothing changed"
        dc exec -T hub python -m wqops.hub.accounts export-owner > "$keep/owner.json.tmp" \
            || die "could not read the owner; nothing changed"
        chmod 600 "$keep"/*.tmp
        mv -f "$keep/trial.json.tmp" "$keep/trial.json" && mv -f "$keep/owner.json.tmp" "$keep/owner.json"
    fi
    log "Deleting the company's containers and data ..."
    dc down -v --remove-orphans
    rm -f "$WD/.demo-loaded" "$WD/backups/demo-golden.tar.gz"
    # a new ERPNext site gets new API keys; the database passwords stay (the volumes are new)
    sed -i '/^WQO_INSTALLED=/d; /^WQO_ERP_API_KEY=/d; /^WQO_ERP_API_SECRET=/d' "$WD/.env"
    ;;
in)
    [ -f "$keep/owner.json" ] || { log "nothing kept to put back"; exit 0; }
    log "Putting back the trial accounts and the owner's password ..."
    dc exec -T hub python -m wqops.hub.trial import < "$keep/trial.json" || die "could not put the trial accounts back (kept in $keep)"
    dc exec -T hub python -m wqops.hub.accounts import-owner < "$keep/owner.json" \
        || die "could not put the owner's password back (kept in $keep)"
    rm -rf "$keep"
    ;;
*) die "usage: ./demo-reinstall.sh out|in" ;;
esac
