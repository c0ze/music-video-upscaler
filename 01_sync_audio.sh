#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT="$SCRIPT_DIR"
# shellcheck source=lib/pipeline.sh
source "${REPO_ROOT}/lib/pipeline.sh"

require_cmd ffmpeg
require_cmd ffprobe

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <input_video> <input_audio> [youtube_url]" >&2
  exit 1
fi

INPUT_VIDEO="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
INPUT_AUDIO="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
YOUTUBE_URL="${3:-}"

video_dir="$(dirname "$INPUT_VIDEO")"
video_base="$(basename "$INPUT_VIDEO")"
video_base="${video_base%.*}"
synced_audio="${video_dir}/${video_base}_synced.flac"
yt_audio="${video_dir}/${video_base}_youtube_audio.wav"

YT_DLP="$(pipeline_resolve_ytdlp)"

echo "Syncing audio..."
echo "Video: $INPUT_VIDEO"
echo "Audio: $INPUT_AUDIO"

if [[ -n "$YOUTUBE_URL" && ! -f "$yt_audio" ]]; then
  echo "Downloading YouTube audio..."
  if command -v "$YT_DLP" >/dev/null 2>&1 || [[ -x "$YT_DLP" ]]; then
    "$YT_DLP" -x --audio-format wav -o "$yt_audio" "$YOUTUBE_URL" >/dev/null 2>&1 || true
  else
    echo "Warning: yt-dlp not found; skipping YouTube download." >&2
  fi
fi

if [[ -f "$yt_audio" ]]; then
  video_silence="$(pipeline_silence_start_seconds "$yt_audio")"
else
  video_silence="$(pipeline_silence_start_seconds "$INPUT_VIDEO")"
fi

flac_silence="$(pipeline_silence_start_seconds "$INPUT_AUDIO")"

add_silence="$(awk -v v="$video_silence" -v f="$flac_silence" 'BEGIN { printf "%.6f", v - f }')"

echo "Video silence: $video_silence s"
echo "FLAC silence:  $flac_silence s"
echo "Offset:        $add_silence s"

if awk -v x="$add_silence" 'BEGIN { exit !(x > 0.01) }'; then
  echo "Adding silence to FLAC..."
  ffmpeg -y -hide_banner -nostdin -f lavfi -t "$add_silence" -i "anullsrc=channel_layout=stereo:sample_rate=44100" -i "$INPUT_AUDIO" \
    -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1[out]" -map "[out]" -c:a flac "$synced_audio" >/dev/null 2>&1
  echo "Created: $synced_audio"
else
  echo "No silence needed. Copying original."
  cp -f "$INPUT_AUDIO" "$synced_audio"
fi
