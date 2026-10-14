#!/usr/bin/env bash
# Restore from a backup: ./restore.sh backups/wqo-<time>.tar.gz [--yes]
# Restores the hub database, the document library files and ERPNext. The configuration in the backup (.env, company manifest) is unpacked into
# backups/restore-<time>/ for comparison and is NOT copied over the current one.
. "$(dirname "$0")/lib.sh"
arg=${1:?usage: ./restore.sh backups/wqo-<time>.tar.gz [--yes]}
f=$(abspath "$arg")
[ -f "$f" ] || f="$WD/$arg"              # also accept a path relative to the install directory
[ -f "$f" ] || die "no such backup: $arg"
work="backups/restore-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$work" && tar -xzf "$f" -C "$work"
if [ "${2:-}" != "--yes" ]; then
    read -r -p "This overwrites the current hub and ERPNext data. Type yes to continue: " ok
    [ "$ok" = yes ] || die "not restored"
fi
log "Restoring the hub database..."
dc stop hub
dc exec -T db pg_restore -U wqo -d wqo --clean --if-exists < "$work/wqo.dump" || true
if [ -f "$work/hub-files.tar" ]; then             # backups made before the document library have none
    log "Restoring the document library files..."
    dc run --rm --no-deps -T --entrypoint sh hub -c 'find /data/files -mindepth 1 -delete && tar -xf - -C /data' \
        < "$work/hub-files.tar"
fi
log "Restoring ERPNext..."
dc exec -T erp-backend bash -c 'rm -rf /tmp/rs && mkdir -p /tmp/rs' && dc exec -T erp-backend bash -c 'cd /tmp/rs && tar -xf -' < "$work/erpnext.tar"
db=$(dc exec -T erp-backend bash -c 'ls -t /tmp/rs/*-database.sql.gz | head -n 1')
pub=$(dc exec -T erp-backend bash -c 'ls -t /tmp/rs/*-files.tar 2>/dev/null | grep -v private | head -n 1' || true)
priv=$(dc exec -T erp-backend bash -c 'ls -t /tmp/rs/*-private-files.tar 2>/dev/null | head -n 1' || true)
dc exec -T erp-backend bench --site frontend restore "$db" --db-root-username root \
    --db-root-password "$(envval ERP_DB_ROOT_PASSWORD)" ${pub:+--with-public-files "$pub"} ${priv:+--with-private-files "$priv"}
dc up -d hub
log "Restore done; the configuration from the backup is in $work/ (env, config.tar)"
