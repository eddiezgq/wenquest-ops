#!/usr/bin/env bash
# Which CI jobs run (private repository: minutes are billed). Writes to $GITHUB_OUTPUT:
#   install  the full install on a clean machine (about 15 minutes)
# Runs when deployment-related files change, nightly when main has new commits, on manual runs, or with the PR label
# full-ci. Env: WF (workflow file), BASE (PR base or previous commit), LABELS (comma separated), GH_TOKEN.
set -euo pipefail
emit() {
  echo "install=$1" >> "$GITHUB_OUTPUT"
  echo "::notice title=CI scope::install=$1 (${GITHUB_EVENT_NAME:-?}, base ${BASE:-none})"   # readable via the API
}
case "$GITHUB_EVENT_NAME" in
  workflow_dispatch) emit true; exit 0 ;;
  schedule)
    last=$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows/$WF/runs?event=schedule&status=success&per_page=1" \
           --jq '.workflow_runs[0].head_sha // ""' 2>/dev/null || echo "")
    if [ "$last" = "$GITHUB_SHA" ]; then echo "no new commits since the last nightly run"; emit false; else emit true; fi
    exit 0 ;;
esac
case ",${LABELS:-}," in *,full-ci,*) emit true; exit 0 ;; esac
if [ -z "${BASE:-}" ] || [ "$BASE" = "0000000000000000000000000000000000000000" ] || ! git cat-file -e "$BASE^{commit}" 2>/dev/null; then
  emit true; exit 0
fi
files=$(git diff --name-only "$BASE" "$GITHUB_SHA")
# Here-strings, not pipes: with pipefail, `echo | grep -q` fails when grep stops reading early (SIGPIPE).
head -n 50 <<< "$files"
if grep -qE '^(deploy/|Dockerfile|\.dockerignore|wqops/(erp|erp_setup|company)\.py|wqops/hub/|wqops/ontology/|wqops/demo/|web/|companies/|pyproject\.toml|\.github/)' <<< "$files"; then
  emit true
else
  emit false
fi
