#!/usr/bin/env bash
# Filename sanitization (POSIX): lowercase, brackets/parens/spaces to underscores.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <directory>" >&2
  exit 1
fi

DIR="$(cd "$1" && pwd)"
echo "Sanitizing files in: $DIR"

find "$DIR" -maxdepth 1 -mindepth 1 | while read -r path; do
  base="$(basename "$path")"
  # Skip hidden
  [[ "$base" == .* ]] && continue

  new=$(echo "$base" | tr '[:upper:]' '[:lower:]' | sed -e "s/[][()[:space:]'\"]/_/g" | sed -e 's/__*/_/g' | sed -e 's/^_//' | sed -e 's/_$//')
  if [[ "$base" != "$new" ]]; then
    echo "Renaming: '$base' -> '$new'"
    mv "$path" "$(dirname "$path")/$new"
  fi
done

echo "Sanitization complete"
