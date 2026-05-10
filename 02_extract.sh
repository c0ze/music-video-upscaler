#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

require_cmd ffmpeg

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <input_video> [output_frames_dir]" >&2
  exit 1
fi

INPUT_VIDEO="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUTPUT_FRAMES_DIR="${2:-}"

if [[ -z "$OUTPUT_FRAMES_DIR" ]]; then
  OUTPUT_FRAMES_DIR="$(dirname "$INPUT_VIDEO")/tmp_frames"
fi

mkdir -p "$OUTPUT_FRAMES_DIR"
rm -f "${OUTPUT_FRAMES_DIR}"/*.png 2>/dev/null || true

echo "Extracting frames from $INPUT_VIDEO to $OUTPUT_FRAMES_DIR"
ffmpeg -hide_banner -nostdin -i "$INPUT_VIDEO" -f image2 "${OUTPUT_FRAMES_DIR}/%06d.png" >/dev/null 2>&1
echo "Extraction complete"
