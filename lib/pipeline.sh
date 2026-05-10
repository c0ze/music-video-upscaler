#!/usr/bin/env bash
# Shared helpers for POSIX pipeline scripts (Linux / macOS).
# Source from repo-root scripts after optional: export REPO_ROOT
# shellcheck shell=bash

if [[ -z "${REPO_ROOT:-}" ]]; then
  if [[ -n "${BASH_SOURCE[1]:-}" ]]; then
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  else
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
  export REPO_ROOT
fi

pipeline_tools_dir() {
  echo "${REPO_ROOT}/tools"
}

pipeline_resolve_ytdlp() {
  if command -v yt-dlp >/dev/null 2>&1; then
    echo "yt-dlp"
    return 0
  fi
  local t
  t="$(pipeline_tools_dir)/yt-dlp"
  if [[ -x "$t" ]]; then
    echo "$t"
    return 0
  fi
  echo "yt-dlp"
}

pipeline_resolve_realesrgan() {
  if [[ -n "${REALESRGAN_BIN:-}" && -x "${REALESRGAN_BIN}" ]]; then
    echo "${REALESRGAN_BIN}"
    return 0
  fi
  local t
  t="$(pipeline_tools_dir)/realesrgan-ncnn-vulkan"
  if [[ -x "$t" ]]; then
    echo "$t"
    return 0
  fi
  if command -v realesrgan-ncnn-vulkan >/dev/null 2>&1; then
    echo "realesrgan-ncnn-vulkan"
    return 0
  fi
  echo ""
}

require_cmd() {
  local c="$1"
  if ! command -v "$c" >/dev/null 2>&1; then
    echo "Error: required command not found: $c" >&2
    echo "Run ./install-dependencies.sh or install $c manually." >&2
    exit 1
  fi
}

# Parse silence_end from ffmpeg silencedetect on stderr
pipeline_silence_start_seconds() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "0.0"
    return 0
  fi
  local out
  out="$(ffmpeg -hide_banner -nostdin -i "$file" -t 5 -af "silencedetect=n=-50dB:d=0.01" -f null - 2>&1)" || true
  if echo "$out" | grep -q 'silence_end:'; then
    echo "$out" | grep 'silence_end:' | tail -1 | sed -n 's/.*silence_end: *\([0-9.]*\).*/\1/p'
  else
    echo "0.0"
  fi
}

pipeline_ffprobe_fps() {
  local video="$1"
  ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$video" | tr -d '\r'
}

pipeline_ffprobe_duration() {
  local f="$1"
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" | tr -d '\r'
}

# Portable file size (bytes)
pipeline_file_size() {
  local f="$1"
  if stat --version >/dev/null 2>&1; then
    stat -c%s "$f"
  else
    stat -f%z "$f"
  fi
}

# Largest video (webm/mkv/mp4) by size under directory (non-recursive: use maxdepth 1 in find)
# Original Windows script used -Recurse; we match that with full recursive find.
pipeline_largest_video() {
  local dir="$1"
  local best="" best_sz=0 f sz
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    sz=$(pipeline_file_size "$f")
    if [[ "$sz" -gt "$best_sz" ]]; then
      best_sz=$sz
      best=$f
    fi
  done < <(find "$dir" -type f \( -iname '*.webm' -o -iname '*.mkv' -o -iname '*.mp4' \) 2>/dev/null | LC_ALL=C sort)
  echo "$best"
}

pipeline_largest_source_audio() {
  local dir="$1"
  local best="" best_sz=0 f sz bn
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    bn=$(basename "$f")
    case "$bn" in
      *_synced*) continue ;;
      *_youtube_audio*) continue ;;
    esac
    sz=$(pipeline_file_size "$f")
    if [[ "$sz" -gt "$best_sz" ]]; then
      best_sz=$sz
      best=$f
    fi
  done < <(find "$dir" -type f \( -iname '*.flac' -o -iname '*.wav' \) 2>/dev/null | LC_ALL=C sort)
  echo "$best"
}
