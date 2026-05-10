#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

REALESRGAN="$(pipeline_resolve_realesrgan)"
if [[ -z "$REALESRGAN" ]]; then
  echo "Error: realesrgan-ncnn-vulkan not found. Install via ./install-dependencies.sh or set REALESRGAN_BIN." >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <input_frames_dir> [output_upscaled_dir] [scale] [model]" >&2
  exit 1
fi

INPUT_FRAMES_DIR="$(cd "$1" && pwd)"
OUTPUT_UPSCALED_DIR="${2:-}"
SCALE="${3:-4}"
MODEL="${4:-realesrgan-x4plus}"

if [[ -z "$OUTPUT_UPSCALED_DIR" ]]; then
  OUTPUT_UPSCALED_DIR="$(dirname "$INPUT_FRAMES_DIR")/tmp_upscaled_${SCALE}x"
fi

mkdir -p "$OUTPUT_UPSCALED_DIR"

todo_count=0
skip_count=0
batch_dir="$(dirname "$INPUT_FRAMES_DIR")/tmp_frames_batch"
rm -rf "$batch_dir"
mkdir -p "$batch_dir"

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  base="$(basename "$f")"
  if [[ -f "${OUTPUT_UPSCALED_DIR}/${base}" ]]; then
    skip_count=$((skip_count + 1))
  else
    cp -f "$f" "$batch_dir/"
    todo_count=$((todo_count + 1))
  fi
done < <(find "$INPUT_FRAMES_DIR" -maxdepth 1 -type f -name '*.png' -print | LC_ALL=C sort)

if [[ "$todo_count" -eq 0 ]]; then
  echo "All frames already upscaled."
else
  echo "Found $todo_count frames to upscale (skipping $skip_count)..."
  echo "Running Real-ESRGAN on batch..."
  echo "Model: $MODEL (x$SCALE)"
  (
    cd "$REPO_ROOT"
    "$REALESRGAN" -i "$batch_dir" -o "$OUTPUT_UPSCALED_DIR" -n "$MODEL" -s "$SCALE" -f png
  )
fi

rm -rf "$batch_dir"
echo "Upscale complete"
