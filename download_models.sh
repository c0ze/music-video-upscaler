#!/usr/bin/env bash
# Download Real-ESRGAN ncnn-vulkan model files into ./models/.
#
# Idempotent: existing non-empty files are kept unless --force is passed.
# Only requires curl and unzip.
#
# See models/README.md for the catalogue and licensing notes.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
MODELS_DIR="$REPO_ROOT/models"

DO_BASE=1
DO_GENERAL=1
DO_EXTRAS=0
FORCE=0
LIST_ONLY=0

usage() {
  cat <<'USAGE'
Usage: ./download_models.sh [options]

  (no args)        install base set + realesr-general-x4v3 (recommended)
  --base-only      install only the xinntao bundled set
  --no-general     skip realesr-general-x4v3 / -wdn-x4v3
  --extras         additionally install community extras (4xLSDIR, 4xNomos8kSC)
  --force          redownload even if files already exist
  --list           list models currently present in models/ and exit
  -h, --help       show this help and exit
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --base-only)   DO_GENERAL=0; DO_EXTRAS=0 ;;
    --no-general)  DO_GENERAL=0 ;;
    --extras|--all) DO_EXTRAS=1 ;;
    --force)       FORCE=1 ;;
    --list)        LIST_ONLY=1 ;;
    -h|--help)     usage; exit 0 ;;
    *) printf 'unknown argument: %s\n\n' "$1" >&2; usage; exit 2 ;;
  esac
  shift
done

log() { printf '[models] %s\n' "$*"; }
warn() { printf '[models] WARN: %s\n' "$*" >&2; }
err() { printf '[models] ERROR: %s\n' "$*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "required command not found: $1"; exit 1; }
}

list_models() {
  if [ ! -d "$MODELS_DIR" ]; then
    log "models/ does not exist"
    return 0
  fi
  log "models present in $MODELS_DIR:"
  # shellcheck disable=SC2010
  ls "$MODELS_DIR" 2>/dev/null \
    | grep -E '\.(bin|param)$' \
    | sed -E 's/\.(bin|param)$//' \
    | sort -u \
    | sed 's/^/  - /'
}

# Idempotent file fetch with retries.
# Args: URL DEST
fetch() {
  url="$1"; dest="$2"
  if [ -s "$dest" ] && [ "$FORCE" -ne 1 ]; then
    return 0
  fi
  tmp="$dest.part"
  curl -fL --retry 4 --retry-delay 2 --progress-bar -o "$tmp" "$url"
  mv "$tmp" "$dest"
}

# ---------- base set: xinntao official ncnn-vulkan v0.2.5.0 zip ----------

NCNN_ZIP_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"

BASE_MODELS="
realesrgan-x4plus
realesrgan-x4plus-anime
realesr-animevideov3-x2
realesr-animevideov3-x3
realesr-animevideov3-x4
"

base_all_present() {
  for name in $BASE_MODELS; do
    [ -s "$MODELS_DIR/$name.bin" ] && [ -s "$MODELS_DIR/$name.param" ] || return 1
  done
  return 0
}

install_base() {
  if [ "$FORCE" -ne 1 ] && base_all_present; then
    log "base models already present (use --force to redownload)"
    return 0
  fi
  log "downloading xinntao Real-ESRGAN ncnn-vulkan v0.2.5.0"
  tmpdir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" EXIT

  fetch "$NCNN_ZIP_URL" "$tmpdir/r.zip"
  unzip -q -o "$tmpdir/r.zip" 'models/*' -d "$tmpdir"

  for name in $BASE_MODELS; do
    for ext in bin param; do
      src="$tmpdir/models/$name.$ext"
      dst="$MODELS_DIR/$name.$ext"
      if [ ! -s "$src" ]; then
        warn "missing in zip: $name.$ext"
        continue
      fi
      if [ -s "$dst" ] && [ "$FORCE" -ne 1 ]; then
        log "  keep    $name.$ext"
        continue
      fi
      cp "$src" "$dst"
      log "  install $name.$ext"
    done
  done

  rm -rf "$tmpdir"
  trap - EXIT
}

# ---------- realesr-general-x4v3 (community ncnn from upscayl) ------------

UPSCAYL_RAW="https://raw.githubusercontent.com/upscayl/custom-models/main/models"

# logical_name | upstream_basename
GENERAL_MAP="
realesr-general-x4v3|RealESRGAN_General_x4_v3
realesr-general-wdn-x4v3|RealESRGAN_General_WDN_x4_v3
"

install_general() {
  log "downloading realesr-general-x4v3 from upscayl/custom-models"
  printf '%s\n' "$GENERAL_MAP" | while IFS='|' read -r dst src; do
    [ -z "$dst" ] && continue
    for ext in bin param; do
      destfile="$MODELS_DIR/$dst.$ext"
      if [ -s "$destfile" ] && [ "$FORCE" -ne 1 ]; then
        log "  keep    $dst.$ext"
        continue
      fi
      fetch "$UPSCAYL_RAW/$src.$ext" "$destfile"
      log "  install $dst.$ext"
    done
  done
}

# ---------- optional extras ----------------------------------------------

EXTRA_MODELS="
4xLSDIR
4xNomos8kSC
"

install_extras() {
  log "downloading community extras"
  for name in $EXTRA_MODELS; do
    for ext in bin param; do
      destfile="$MODELS_DIR/$name.$ext"
      if [ -s "$destfile" ] && [ "$FORCE" -ne 1 ]; then
        log "  keep    $name.$ext"
        continue
      fi
      fetch "$UPSCAYL_RAW/$name.$ext" "$destfile"
      log "  install $name.$ext"
    done
  done
}

# ---------- verification --------------------------------------------------

verify_pairs() {
  missing=0
  for f in "$MODELS_DIR"/*.bin; do
    [ -e "$f" ] || continue
    base="${f%.bin}"
    if [ ! -s "$base.param" ]; then
      warn "orphan .bin without .param: $(basename "$f")"
      missing=1
    fi
  done
  for f in "$MODELS_DIR"/*.param; do
    [ -e "$f" ] || continue
    base="${f%.param}"
    if [ ! -s "$base.bin" ]; then
      warn "orphan .param without .bin: $(basename "$f")"
      missing=1
    fi
  done
  return $missing
}

# ---------- main ----------------------------------------------------------

if [ "$LIST_ONLY" -eq 1 ]; then
  list_models
  exit 0
fi

require_cmd curl
require_cmd unzip
mkdir -p "$MODELS_DIR"

[ "$DO_BASE" -eq 1 ]    && install_base
[ "$DO_GENERAL" -eq 1 ] && install_general
[ "$DO_EXTRAS" -eq 1 ]  && install_extras

if verify_pairs; then
  log "all model files have matching .bin/.param pairs"
fi

log "done"
list_models
