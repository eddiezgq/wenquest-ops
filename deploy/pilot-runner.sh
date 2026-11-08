#!/usr/bin/env bash
# Open the pilot companies the WenQuest platform asks for (ADR-0025, step 25c). Runs every minute from the deploy
# user's crontab, in the demo installation (e.g. /opt/wenquest/qms). The platform's gateway and this script share
# one folder (WQO_PILOT_QUEUE, default /opt/wenquest/pilot-queue):
#   req-<id>.json    the gateway: a company to open {id, name, contact, email, lang}
#   state-<id>.json  this script: installing / active / failed (+ error)
#   res-<id>.json    this script: the owner's sign-in; the gateway emails it and deletes the file at once
#   cmd-<id>.json    the gateway: {cmd: stop|start}
#   trial-<id>.json  the gateway: a trial account in the demo company {id, name, email} (ADR-0027; only when the demo's
#                    .env has WQO_DEMO_TRIAL=1) -> res-trial-<id>.json {id, email, password, expires, url} or
#                    {id, error}
#   host.json        this script, every run: free memory, so the platform can refuse when the server is full
#   ./pilot-runner.sh
. "$(dirname "$0")/lib.sh"

Q=${WQO_PILOT_QUEUE:-/opt/wenquest/pilot-queue}
[ -d "$Q" ] || exit 0
exec 8>/tmp/wqo-pilot-runner.lock
flock -n 8 || exit 0                         # the previous run is still installing

put() {   # write a file the gateway (another user) reads and may delete: whole, then renamed
    local tmp="$Q/.$1.tmp"
    printf '%s\n' "$2" > "$tmp" && chmod 644 "$tmp" && mv -f "$tmp" "$Q/$1"
}
field() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"; }

free_mb=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
put host.json "{\"mem_free_mb\": $free_mb, \"ts\": $(date +%s)}"

for req in "$Q"/req-*.json; do
    [ -f "$req" ] || continue
    id=$(field "$req" id) || { mv -f "$req" "$req.bad"; continue; }
    work="$Q/work-$id.json"
    mv -f "$req" "$work"
    put "state-$id.json" "{\"id\": \"$id\", \"status\": \"installing\"}"
    log "Opening pilot company $id ..."
    out="$WD/pilot-$id.log"
    if "$WD/tenant.sh" new "$id" --name "$(field "$work" name)" --contact "$(field "$work" contact)" \
            --email "$(field "$work" email)" --lang "$(field "$work" lang)" --result "$Q/.res-$id.tmp" > "$out" 2>&1; then
        chmod 644 "$Q/.res-$id.tmp" && mv -f "$Q/.res-$id.tmp" "$Q/res-$id.json"
        put "state-$id.json" "{\"id\": \"$id\", \"status\": \"active\"}"
        log "Pilot company $id is open"
    else
        err=$(tail -n 8 "$out" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
        put "state-$id.json" "{\"id\": \"$id\", \"status\": \"failed\", \"error\": $err}"
        log "Opening $id failed (see $out)"
    fi
    rm -f "$work"
done

for t in "$Q"/trial-*.json; do              # ADR-0027: an account in the shared demo company, in seconds
    [ -f "$t" ] || continue
    id=$(field "$t" id) || { mv -f "$t" "$t.bad"; continue; }
    if [ "$(envval WQO_DEMO_TRIAL)" != 1 ]; then
        put "res-trial-$id.json" "{\"id\": \"$id\", \"error\": \"trial accounts are not open on this server\"}"
    elif out=$(dc exec -T hub python -m wqops.hub.trial add --name "$(field "$t" name)" --email "$(field "$t" email)" 2>&1); then
        url="https://$(envval WQO_DOMAIN)"
        put "res-trial-$id.json" "$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); d.update(id=sys.argv[2], url=sys.argv[3]); print(json.dumps(d, ensure_ascii=False))' "$out" "$id" "$url")"
        log "Trial account $id opened"
    else
        put "res-trial-$id.json" "$(python3 -c 'import json,sys; print(json.dumps({"id": sys.argv[1], "error": sys.argv[2][-300:]}, ensure_ascii=False))' "$id" "$out")"
        log "Trial account $id refused: $out"
    fi
    rm -f "$t"
done

for c in "$Q"/cmd-*.json; do
    [ -f "$c" ] || continue
    id=$(field "$c" id) && what=$(field "$c" cmd) || { rm -f "$c"; continue; }
    case "$what" in stop|start) "$WD/tenant.sh" "$what" "$id" || log "could not $what $id" ;; esac
    rm -f "$c"
done
