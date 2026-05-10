#!/usr/bin/env bash
# Monitor PNG frame count for long-running upscales (POSIX).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

TARGET_FRAMES="${1:-8668}"
DIRECTORY="${2:-./tmp_upscaled_4x}"

echo "Monitoring upscale progress..."
echo "Target: $TARGET_FRAMES frames"
echo "Directory: $DIRECTORY"
echo "Press Ctrl+C to stop."

while true; do
  if [[ -d "$DIRECTORY" ]]; then
    count=$(find "$DIRECTORY" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')
    if [[ -z "${count}" ]]; then count=0; fi
    percent="$(awk -v c="$count" -v t="$TARGET_FRAMES" 'BEGIN { if (t <= 0) { print 0 } else { printf "%.2f", (c / t) * 100 } }')"
    ts="$(date '+%H:%M:%S')"
    echo "[$ts] Frames: $count / $TARGET_FRAMES (${percent}%)"
    if [[ "$count" -ge "$TARGET_FRAMES" ]]; then
      echo "Upscale complete!"
      break
    fi
  else
    echo "Directory not found yet..."
  fi
  sleep 30
done
