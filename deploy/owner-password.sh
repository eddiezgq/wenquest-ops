#!/usr/bin/env bash
# Set (or change) the password of the owner in company.yaml. Asks for it; nothing is shown or kept in the shell history.
#   ./owner-password.sh
. "$(dirname "$0")/lib.sh"
[ -t 0 ] || die "run this in a terminal: it asks for the password"
read -r -s -p "Password for the owner (10+ characters, letters and digits): " pw; echo
read -r -s -p "Again: " pw2; echo
[ "$pw" = "$pw2" ] || die "the two passwords differ"
printf '%s\n' "$pw" | dc exec -T hub python -m wqops.hub.accounts set-owner-password
