#!/usr/bin/env bash
#
# Upscale a video using Real-ESRGAN and combine with high-quality audio (Linux/macOS).
#
# Usage:
#   ./upscale_video.sh <input_video> <input_audio> [youtube_url]
#
# Environment overrides:
#   SCALE=4|2  OUTPUT_FORMAT=mkv|mp4  MODEL=realesr-general-x4v3
#   SKIP_EXTRACT=1  SKIP_UPSCALE=1  SKIP_AUDIO_SYNC=1
#
# For stronger denoising on very noisy YouTube sources, override:
#   MODEL=realesr-general-wdn-x4v3
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

SCALE="${SCALE:-4}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-mkv}"
MODEL="${MODEL:-realesr-general-x4v3}"

if [[ "$SCALE" != "2" && "$SCALE" != "4" ]]; then
  echo "SCALE must be 2 or 4" >&2
  exit 1
fi
if [[ "$OUTPUT_FORMAT" != "mkv" && "$OUTPUT_FORMAT" != "mp4" ]]; then
  echo "OUTPUT_FORMAT must be mkv or mp4" >&2
  exit 1
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <input_video> <input_audio> [youtube_url]" >&2
  exit 1
fi

INPUT_VIDEO="$1"
INPUT_AUDIO="$2"
YOUTUBE_URL="${3:-}"

resolve_existing_path() {
  local p="$1"
  if [[ -f "$p" ]]; then
    echo "$(cd "$(dirname "$p")" && pwd)/$(basename "$p")"
    return 0
  fi
  if [[ -f "$(pwd)/$p" ]]; then
    echo "$(cd "$(dirname "$(pwd)/$p")" && pwd)/$(basename "$p")"
    return 0
  fi
  if [[ -f "${REPO_ROOT}/$p" ]]; then
    echo "$(cd "$(dirname "${REPO_ROOT}/$p")" && pwd)/$(basename "$p")"
    return 0
  fi
  echo ""
}

INPUT_VIDEO_PATH="$(resolve_existing_path "$INPUT_VIDEO")"
INPUT_AUDIO_PATH="$(resolve_existing_path "$INPUT_AUDIO")"

if [[ -z "$INPUT_VIDEO_PATH" || ! -f "$INPUT_VIDEO_PATH" ]]; then
  echo "ERROR: input video not found: $INPUT_VIDEO" >&2
  exit 1
fi
if [[ -z "$INPUT_AUDIO_PATH" || ! -f "$INPUT_AUDIO_PATH" ]]; then
  echo "ERROR: input audio not found: $INPUT_AUDIO" >&2
  exit 1
fi

REALESRGAN="$(pipeline_resolve_realesrgan)"
if [[ -z "$REALESRGAN" ]]; then
  echo "ERROR: realesrgan-ncnn-vulkan not found. Run ./install-dependencies.sh or set REALESRGAN_BIN." >&2
  exit 1
fi

YT_DLP="$(pipeline_resolve_ytdlp)"

SOURCE_DIR="$(dirname "$INPUT_VIDEO_PATH")"
VIDEO_BASE="$(basename "$INPUT_VIDEO_PATH")"
VIDEO_BASE="${VIDEO_BASE%.*}"

FRAMES_DIR="${SOURCE_DIR}/tmp_frames"
UPSCALED_DIR="${SOURCE_DIR}/tmp_upscaled_${SCALE}x"
OUTPUT_DIR="${SOURCE_DIR}/output"
ENGINE="realesrgan"
OUTPUT_NAME="${VIDEO_BASE}_${ENGINE}_${MODEL}_${SCALE}x_HQ"
OUTPUT_VIDEO="${OUTPUT_DIR}/${OUTPUT_NAME}.${OUTPUT_FORMAT}"

require_cmd ffmpeg
require_cmd ffprobe

FRAME_RATE="$(pipeline_ffprobe_fps "$INPUT_VIDEO_PATH")"
echo "Native framerate: $FRAME_RATE"

echo "============================================"
echo "  Video upscaling with Real-ESRGAN"
echo "============================================"
echo "  Input video:  $INPUT_VIDEO_PATH"
echo "  Input audio:  $INPUT_AUDIO_PATH"
echo "  Scale:        ${SCALE}x"
echo "  Framerate:    $FRAME_RATE"
echo "  Model:        $MODEL"
echo "  Format:       $OUTPUT_FORMAT"
echo "  Output:       $OUTPUT_VIDEO"
echo ""

mkdir -p "$FRAMES_DIR" "$UPSCALED_DIR" "$OUTPUT_DIR"

SYNCED_AUDIO_PATH="$INPUT_AUDIO_PATH"

if [[ -z "${SKIP_AUDIO_SYNC:-}" ]]; then
  echo ""
  echo "Audio sync detection..."
  video_duration="$(pipeline_ffprobe_duration "$INPUT_VIDEO_PATH")"
  flac_duration="$(pipeline_ffprobe_duration "$INPUT_AUDIO_PATH")"
  echo "  Video duration: $video_duration s"
  echo "  Audio duration: $flac_duration s"

  yt_audio_path="${SOURCE_DIR}/${VIDEO_BASE}_youtube_audio.wav"

  if [[ -f "$yt_audio_path" ]]; then
    echo "  Using existing YouTube audio: $yt_audio_path"
  elif [[ -n "$YOUTUBE_URL" ]]; then
    echo "  Downloading YouTube audio..."
    if command -v "$YT_DLP" >/dev/null 2>&1 || [[ -x "$YT_DLP" ]]; then
      "$YT_DLP" -x --audio-format wav -o "$yt_audio_path" "$YOUTUBE_URL" >/dev/null 2>&1 || true
    fi
    if [[ ! -f "$yt_audio_path" ]]; then
      echo "  WARNING: failed to download YouTube audio; using video track for silence." >&2
      yt_audio_path=""
    fi
  else
    yt_audio_path=""
  fi

  if [[ -n "$yt_audio_path" && -f "$yt_audio_path" ]]; then
    video_silence_end="$(pipeline_silence_start_seconds "$yt_audio_path")"
  else
    video_silence_end="$(pipeline_silence_start_seconds "$INPUT_VIDEO_PATH")"
  fi

  flac_silence_end="$(pipeline_silence_start_seconds "$INPUT_AUDIO_PATH")"

  silence_to_add="$(awk -v v="$video_silence_end" -v f="$flac_silence_end" 'BEGIN { printf "%.6f", v - f }')"
  echo "  Video audio starts at: $video_silence_end s"
  echo "  FLAC audio starts at:  $flac_silence_end s"

  if awk -v x="$silence_to_add" 'BEGIN { exit !(x > 0.01) }'; then
    echo "  Adding ${silence_to_add}s silence to FLAC start..."
    SYNCED_AUDIO_PATH="${SOURCE_DIR}/${VIDEO_BASE}_synced.flac"
    ffmpeg -y -hide_banner -nostdin -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=44100" -t "$silence_to_add" -i "$INPUT_AUDIO_PATH" \
      -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1[out]" -map "[out]" -c:a flac "$SYNCED_AUDIO_PATH" >/dev/null 2>&1 || SYNCED_AUDIO_PATH="$INPUT_AUDIO_PATH"
  elif awk -v x="$silence_to_add" 'BEGIN { exit !(x < -0.01) }'; then
    echo "  FLAC has more leading silence than video; no padding applied."
  else
    echo "  Audio timing already matched."
  fi

  vd="$(awk -v v="$video_duration" 'BEGIN { print v+0 }')"
  fd="$(awk -v v="$flac_duration" 'BEGIN { print v+0 }')"
  diff="$(awk -v v="$vd" -v f="$fd" 'BEGIN { d=v-f; if (d < 0) d=-d; print d }')"
  awk -v d="$diff" 'BEGIN { exit !(d > 1.0) }' && {
    echo ""
    echo "WARNING: audio/video duration mismatch (~${diff}s). Manual sync may be needed."
    echo ""
  }
else
  echo "Audio sync skipped."
fi

echo ""
echo "Step 1/3: extracting frames..."
if [[ -z "${SKIP_EXTRACT:-}" ]]; then
  rm -f "${FRAMES_DIR}"/*.png 2>/dev/null || true
  ffmpeg -hide_banner -nostdin -i "$INPUT_VIDEO_PATH" -f image2 "${FRAMES_DIR}/%06d.png" >/dev/null 2>&1
  frame_count=$(find "$FRAMES_DIR" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')
  echo "  Extracted $frame_count frames."
else
  echo "  Skipped (existing frames)."
fi

frame_count=$(find "$FRAMES_DIR" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')
echo "  Total frames: $frame_count"

echo ""
echo "Step 2/3: upscaling (${SCALE}x)..."
if [[ -z "${SKIP_UPSCALE:-}" ]]; then
  rm -f "${UPSCALED_DIR}"/*.png 2>/dev/null || true
  (
    cd "$REPO_ROOT"
    "$REALESRGAN" -i "$FRAMES_DIR" -o "$UPSCALED_DIR" -n "$MODEL" -s "$SCALE" -f png
  )
  up_count=$(find "$UPSCALED_DIR" -maxdepth 1 -type f -name '*.png' | wc -l | tr -d ' ')
  echo "  Upscaled $up_count frames."
  if [[ "$up_count" != "$frame_count" ]]; then
    echo "  WARNING: frame count mismatch (expected $frame_count, got $up_count)." >&2
  fi
else
  echo "  Skipped (existing upscaled frames)."
fi

echo ""
echo "Step 3/3: muxing..."
rm -f "$OUTPUT_VIDEO"
if [[ "$OUTPUT_FORMAT" == "mkv" ]]; then
  ffmpeg -hide_banner -nostdin -framerate "$FRAME_RATE" -i "${UPSCALED_DIR}/%06d.png" -i "$SYNCED_AUDIO_PATH" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -map 0:v:0 -map 1:a:0 -y "$OUTPUT_VIDEO"
else
  ffmpeg -hide_banner -nostdin -framerate "$FRAME_RATE" -i "${UPSCALED_DIR}/%06d.png" -i "$SYNCED_AUDIO_PATH" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a aac -b:a 320k -map 0:v:0 -map 1:a:0 -shortest -y "$OUTPUT_VIDEO"
fi

if [[ ! -f "$OUTPUT_VIDEO" ]]; then
  echo "ERROR: output was not created." >&2
  exit 1
fi

sz="$(pipeline_file_size "$OUTPUT_VIDEO")"
sz_mb="$(awk -v b="$sz" 'BEGIN { printf "%.1f", b/1024/1024 }')"
echo ""
echo "COMPLETE: $OUTPUT_VIDEO (${sz_mb} MB)"
