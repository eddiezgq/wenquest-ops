#!/usr/bin/env bash
# Put the company's AI key into .env and restart the hub (ADR-0023, ADR-0024). Asks for the key; nothing is shown.
# In China (WQO_DEPLOYMENT=cn) it is the DeepSeek key; elsewhere the Anthropic key, unless WQO_AI_PROVIDER=deepseek.
#   ./ai-key.sh
. "$(dirname "$0")/lib.sh"
[ -t 0 ] || die "run this in a terminal: it asks for the key"
if [ "$(envval WQO_DEPLOYMENT)" = cn ] || [ "$(envval WQO_AI_PROVIDER)" = deepseek ]; then k=WQO_DEEPSEEK_API_KEY; name=DeepSeek
else k=WQO_ANTHROPIC_API_KEY; name=Anthropic; fi
read -r -s -p "$name API key: " key; echo
[ -n "$key" ] || die "no key given"
envset "$k" "$key"
exec 9>/tmp/wenquest-deploy.lock           # on a shared server, never while another deployment restarts its containers
flock -w 1500 9 || die "another deployment holds the lock; try again later"
dc up -d hub
log "$name key saved in .env; the hub restarted. The assistant now answers with the model."
