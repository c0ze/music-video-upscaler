#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

require_cmd ffmpeg
require_cmd ffprobe

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <frames_dir> <audio_path> <output_video> [original_video_for_fps]" >&2
  exit 1
fi

FRAMES_DIR="$(cd "$1" && pwd)"
AUDIO_PATH="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
OUTPUT_VIDEO="$3"
ORIGINAL_VIDEO="${4:-}"

parent="$(dirname "$OUTPUT_VIDEO")"
mkdir -p "$parent"

fps="${FPS:-30}"
if [[ -n "$ORIGINAL_VIDEO" && -f "$ORIGINAL_VIDEO" ]]; then
  echo "Extracting FPS from $ORIGINAL_VIDEO..."
  fps="$(pipeline_ffprobe_fps "$ORIGINAL_VIDEO")"
fi

echo "Muxing frames + audio at FPS: $fps"

ffmpeg -hide_banner -nostdin -framerate "$fps" -i "${FRAMES_DIR}/%06d.png" -i "$AUDIO_PATH" \
  -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -map 0:v:0 -map 1:a:0 \
  -y "$OUTPUT_VIDEO"

echo "Done: $OUTPUT_VIDEO"
