#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <target_folder> [youtube_url] [scale] [model]" >&2
  echo "  Default model: realesr-general-x4v3" >&2
  echo "  For stronger denoise: realesr-general-wdn-x4v3" >&2
  exit 1
fi

TARGET_FOLDER="$(cd "$1" && pwd)"
YOUTUBE_URL="${2:-}"
SCALE="${3:-4}"
MODEL="${4:-realesr-general-x4v3}"

echo "Running upscale pipeline on: $TARGET_FOLDER"

"${REPO_ROOT}/00_sanitize.sh" "$TARGET_FOLDER"

video_file="$(pipeline_largest_video "$TARGET_FOLDER")"
audio_file="$(pipeline_largest_source_audio "$TARGET_FOLDER")"

if [[ -z "$video_file" || -z "$audio_file" ]]; then
  echo "Error: could not identify video/audio pair in $TARGET_FOLDER" >&2
  exit 1
fi

echo "Found video: $(basename "$video_file")"
echo "Found audio: $(basename "$audio_file")"

"${REPO_ROOT}/01_sync_audio.sh" "$video_file" "$audio_file" "$YOUTUBE_URL"

frames_dir="${TARGET_FOLDER}/tmp_frames"
"${REPO_ROOT}/02_extract.sh" "$video_file" "$frames_dir"

upscaled_dir="${TARGET_FOLDER}/tmp_upscaled_${SCALE}x"
"${REPO_ROOT}/03_upscale.sh" "$frames_dir" "$upscaled_dir" "$SCALE" "$MODEL"

video_base="$(basename "$video_file")"
video_base="${video_base%.*}"

synced_audio="${TARGET_FOLDER}/${video_base}_synced.flac"

output_name="${video_base}_realesrgan_${MODEL}_${SCALE}x_HQ.mkv"
parent_out="$(dirname "$TARGET_FOLDER")"
output_dir="${parent_out}/METAL_VIDS_UPSCALED_FLAC/$(basename "$TARGET_FOLDER")"
mkdir -p "$output_dir"
final_output="${output_dir}/${output_name}"

"${REPO_ROOT}/04_mux.sh" "$upscaled_dir" "$synced_audio" "$final_output" "$video_file"

echo "Pipeline finished!"
echo "Output: $final_output"
