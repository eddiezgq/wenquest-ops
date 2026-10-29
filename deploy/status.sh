#!/usr/bin/env bash
# Status: services, health check, ERPNext, disk, newest backup. Exit code 1 when something is wrong (for monitoring).
. "$(dirname "$0")/lib.sh"
dc ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'
d=$(envval WQO_DOMAIN); e=$(envval WQO_ERP_DOMAIN)
bad=0
edge() { case ":$(envval WQO_COMPOSE_FILES):" in *:docker-compose.edge.yml:*) return 0 ;; *) return 1 ;; esac; }
check() {
    if edge; then   # behind the server's own Caddy (ADR-0024): ask our Caddy directly, by name
        if dc exec -T caddy wget -q -O /dev/null -T 10 --header "Host: $2" "http://127.0.0.1:80$3" 2>/dev/null
        then echo "$1: ok"; else echo "$1: FAILED"; bad=1; fi
        return
    fi
    if curl -fsk -o /dev/null --max-time 10 --resolve "$2:443:127.0.0.1" "https://$2$3"; then echo "$1: ok"
    else echo "$1: FAILED"; bad=1; fi
}
check "WenQuest Ops https://$d/api/health" "$d" /api/health
check "ERPNext https://$e" "$e" /api/method/ping
echo "Free disk: $(df -Ph "$WD" | awk 'NR==2 {print $4}')"
echo "Newest backup: $(ls -1t backups/wqo-*.tar.gz 2>/dev/null | head -n 1 || echo none)"
exit "$bad"
