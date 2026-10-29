#!/usr/bin/env bash
# Back up the hub database and document files, ERPNext (database and files) and the configuration to
# backups/wqo-<time>.tar.gz.
# Keeps the newest WQO_KEEP (default 14). Run daily from cron, e.g.:
#   echo "30 2 * * * root /opt/wenquest-ops/backup.sh" > /etc/cron.d/wenquest-ops-backup
# WQO_BACKUP_COPY_TO: also copy each backup there (another disk, a mounted bucket).
. "$(dirname "$0")/lib.sh"
ts=$(date +%Y%m%d-%H%M%S)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
log "Backing up the hub database..."
dc exec -T db pg_dump -U wqo -d wqo -Fc > "$work/wqo.dump"
log "Backing up the document library files..."
dc exec -T hub tar -cf - -C /data files > "$work/hub-files.tar"
log "Backing up ERPNext..."
dc exec -T erp-backend bench --site frontend backup --with-files >/dev/null
dc exec -T erp-backend bash -c 'cd sites/frontend/private/backups && tar -cf - $(ls -t | head -n 4)' > "$work/erpnext.tar"
cp .env "$work/env"
tar -cf "$work/config.tar" company Caddyfile* docker-compose*.yml 2>/dev/null || true
tar -czf "backups/wqo-$ts.tar.gz" -C "$work" .
chmod 600 "backups/wqo-$ts.tar.gz"
ls -1t backups/wqo-*.tar.gz | tail -n +"$(( ${WQO_KEEP:-14} + 1 ))" | xargs -r rm -f
[ -z "${WQO_BACKUP_COPY_TO:-}" ] || cp "backups/wqo-$ts.tar.gz" "$WQO_BACKUP_COPY_TO/"
log "Backup done: backups/wqo-$ts.tar.gz"
echo "backups/wqo-$ts.tar.gz"
