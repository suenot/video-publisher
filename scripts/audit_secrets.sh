#!/usr/bin/env bash
# Fail if any tracked (or staged) file looks like a session secret.
set -euo pipefail
PATTERN='(^|/)\.camoufox_profile/|\.camoufox_fp\.pkl$|\.sqlite$|cookies.*\.json$|^debug/'
hits="$(git ls-files | grep -E "$PATTERN" || true)"
staged="$(git diff --cached --name-only | grep -E "$PATTERN" || true)"
if [[ -n "$hits$staged" ]]; then
  echo "SECRET LEAK BLOCKED — these must never be committed:" >&2
  printf '%s\n' "$hits" "$staged" | sed '/^$/d' >&2
  exit 1
fi
echo "secret audit clean"
