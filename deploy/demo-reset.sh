#!/usr/bin/env bash
# The shared demo company goes back to its clean snapshot every night (ADR-0027). Run from the demo installation
# (e.g. /opt/wenquest/qms) when its .env has WQO_DEMO_TRIAL=1:
#   ./demo-reset.sh snapshot    take the clean snapshot now (the first time, and after changing the demo data on purpose)
#   ./demo-reset.sh             the night's run: keep the live trial accounts, restore the snapshot, bring it up to the
#                               running version, take the snapshot again (so it is always clean and current), then put
#                               the trial accounts back and end the ones past their date
# Holds the deployment lock; a failure leaves the demo as it is and the next night tries again.
. "$(dirname "$0")/lib.sh"

GOLD="$WD/backups/demo-golden.tar.gz"
[ "$(envval WQO_DEMO_TRIAL)" = 1 ] || die "trial accounts are not on here (WQO_DEMO_TRIAL=1 in .env)"
exec 9>/tmp/wenquest-deploy.lock
flock -w 3600 9 || die "another deployment holds the lock; the reset waits for the next night"

snapshot() {
    log "Taking the clean snapshot ..."
    out=$(WQO_KEEP=1000 WQO_BACKUP_COPY_TO='' "$WD/backup.sh" 2>&1) || { printf '%s\n' "$out"; die "the snapshot failed"; }
    f=$(ls -t "$WD"/backups/wqo-*.tar.gz | head -n 1)
    mv -f "$f" "$GOLD.tmp" && mv -f "$GOLD.tmp" "$GOLD"
    log "Snapshot: $GOLD"
}

case "${1:-}" in
snapshot) snapshot; exit 0 ;;
"") ;;
*) die "usage: ./demo-reset.sh [snapshot]" ;;
esac

[ -f "$GOLD" ] || { snapshot; exit 0; }            # the first night: today's demo becomes the clean snapshot
keep="$WD/backups/trial-accounts.json"
log "Keeping the trial accounts ..."
dc exec -T hub python -m wqops.hub.trial export > "$keep.tmp" || die "could not read the trial accounts; nothing changed"
mv -f "$keep.tmp" "$keep" && chmod 600 "$keep"
log "Restoring the clean snapshot ..."
"$WD/restore.sh" "$GOLD" --yes || die "the restore stopped; see above"
log "Bringing it up to the running version ..."
WQO_NO_PULL=1 WQO_SKIP_BACKUP=1 "$WD/upgrade.sh" "$(envval WQO_HUB_IMAGE | sed 's/.*://')" || log "WARNING: the upgrade step after the restore failed"
rm -rf "$WD"/backups/restore-*
snapshot                                            # clean and current, before any trial account is back
log "Putting the trial accounts back ..."
dc exec -T hub python -m wqops.hub.trial import < "$keep" || die "could not put the trial accounts back (kept in $keep)"
dc exec -T hub python -m wqops.hub.trial expire || true
log "Demo company reset"
