#!/usr/bin/env bash
# Platform-agnostic dependency installer for the music-video-upscaler toolchain.
# Supports: macOS (Homebrew), Debian/Ubuntu (apt), Fedora (dnf), Arch (pacman),
# Git Bash / MSYS2 on Windows (winget + pip when available).
#
# Usage:
#   ./install-dependencies.sh
#   INSTALL_REALESRGAN=1 ./install-dependencies.sh   # Linux x86_64 only (downloads binary)
#
set -euo pipefail

WITH_WEB=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --with-web) WITH_WEB=1 ;;
    -h|--help)
      cat <<USAGE
Usage: $(basename "$0") [--with-web]

Options:
  --with-web   Also create web/.venv and install web UI dependencies.
USAGE
      exit 0 ;;
    *) ARGS+=("$arg") ;;
  esac
done
if [[ ${#ARGS[@]} -gt 0 ]]; then
  set -- "${ARGS[@]}"
else
  set --
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="${ROOT}/tools"
mkdir -p "${TOOLS}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

log() { printf '%s\n' "$*"; }

need_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    return 1
  fi
  return 0
}

ensure_python_pip() {
  if have_cmd python3; then
    python3 -m pip --version >/dev/null 2>&1 || python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
    python3 -m pip install --user --upgrade yt-dlp
    return 0
  fi
  if have_cmd python; then
    python -m pip install --user --upgrade yt-dlp
    return 0
  fi
  log "Could not install yt-dlp automatically (python/pip missing)."
  return 1
}

download_realesrgan_linux_x64() {
  local url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
  local zip="${TOOLS}/realesrgan-ncnn-vulkan-ubuntu.zip"
  log "Downloading Real-ESRGAN ncnn Vulkan build for Linux x86_64..."
  if have_cmd curl; then
    curl -fsSL -o "$zip" "$url"
  elif have_cmd wget; then
    wget -q -O "$zip" "$url"
  else
    log "Need curl or wget to download Real-ESRGAN."
    exit 1
  fi
  rm -rf "${TOOLS}/realesrgan-ncnn-vulkan-linux"
  mkdir -p "${TOOLS}/realesrgan-ncnn-vulkan-linux"
  if have_cmd unzip; then
    unzip -o "$zip" -d "${TOOLS}/realesrgan-ncnn-vulkan-linux"
  else
    log "unzip is required to extract Real-ESRGAN."
    exit 1
  fi
  local bin
  bin="$(find "${TOOLS}/realesrgan-ncnn-vulkan-linux" -type f -name 'realesrgan-ncnn-vulkan' 2>/dev/null | head -1)"
  if [[ -z "$bin" ]]; then
    bin="$(find "${TOOLS}/realesrgan-ncnn-vulkan-linux" -type f -name 'realesrgan-ncnn-vulkan*' 2>/dev/null | head -1)"
  fi
  if [[ -z "$bin" || ! -f "$bin" ]]; then
    log "Could not locate extracted Real-ESRGAN binary; inspect ${TOOLS}/realesrgan-ncnn-vulkan-linux"
    exit 1
  fi
  chmod +x "$bin"
  ln -sf "$bin" "${TOOLS}/realesrgan-ncnn-vulkan"
  log "Installed Real-ESRGAN to ${TOOLS}/realesrgan-ncnn-vulkan"
}

OS="$(uname -s)"
ARCH="$(uname -m)"

log "Detected OS: ${OS} (${ARCH})"

if ! have_cmd ffmpeg || ! have_cmd ffprobe; then
  case "${OS}" in
    Darwin)
      if ! have_cmd brew; then
        log "Install Homebrew first: https://brew.sh"
        exit 1
      fi
      brew install ffmpeg
      ;;
    Linux)
      if have_cmd apt-get; then
        if need_sudo; then SUDO=sudo; else SUDO=""; fi
        ${SUDO} apt-get update
        ${SUDO} apt-get install -y ffmpeg python3 python3-pip unzip curl
      elif have_cmd dnf; then
        if need_sudo; then SUDO=sudo; else SUDO=""; fi
        ${SUDO} dnf install -y ffmpeg python3 python3-pip unzip curl
      elif have_cmd pacman; then
        if need_sudo; then SUDO=sudo; else SUDO=""; fi
        ${SUDO} pacman -Sy --needed ffmpeg python python-pip unzip curl
      else
        log "Unsupported Linux package manager; install ffmpeg manually."
        exit 1
      fi
      ;;
    MSYS*|MINGW*|CYGWIN_NT*)
      if have_cmd winget; then
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements || log "winget ffmpeg install failed; install FFmpeg manually."
      elif have_cmd choco; then
        choco install ffmpeg -y || true
      else
        log "Install FFmpeg for Windows, then re-run this script."
        exit 1
      fi
      ;;
    *)
      log "Install ffmpeg + ffprobe manually for ${OS}, then re-run."
      exit 1
      ;;
  esac
fi

if ! have_cmd ffmpeg || ! have_cmd ffprobe; then
  log "ffmpeg/ffprobe still not found on PATH after installation attempt."
  exit 1
fi

if ! have_cmd yt-dlp && [[ ! -x "${TOOLS}/yt-dlp" ]]; then
  case "${OS}" in
    Darwin)
      brew install yt-dlp || ensure_python_pip
      ;;
    Linux)
      ensure_python_pip || true
      ;;
    MSYS*|MINGW*|CYGWIN_NT*)
      ensure_python_pip || python -m pip install --user --upgrade yt-dlp || true
      ;;
    *)
      ensure_python_pip || true
      ;;
  esac
fi

if have_cmd yt-dlp || [[ -x "${TOOLS}/yt-dlp" ]]; then
  log "yt-dlp ok"
else
  log "yt-dlp not found. Install with: python3 -m pip install --user yt-dlp"
fi

if [[ "${INSTALL_REALESRGAN:-}" == "1" ]]; then
  if [[ -x "${TOOLS}/realesrgan-ncnn-vulkan" ]]; then
    log "Real-ESRGAN already present in tools/"
  elif [[ "${OS}" == Linux && "${ARCH}" == x86_64 ]]; then
    download_realesrgan_linux_x64
  else
    log "Automatic Real-ESRGAN download is only wired for Linux x86_64."
    log "macOS: build from source or download a Vulkan ncnn build and set REALESRGAN_BIN."
    log "Windows: place realesrgan-ncnn-vulkan.exe under windows\\ (see README)."
  fi
else
  if ! have_cmd realesrgan-ncnn-vulkan && [[ ! -x "${TOOLS}/realesrgan-ncnn-vulkan" ]]; then
    log "Real-ESRGAN ncnn Vulkan not found."
    log "Linux x86_64: re-run with INSTALL_REALESRGAN=1"
    log "Windows: place portable build under windows\\"
    log "macOS: install or build a Vulkan binary and export REALESRGAN_BIN=... or put it in tools/"
  fi
fi

log ""
log "Dependency check:"
have_cmd ffmpeg && log "  ffmpeg: OK" || log "  ffmpeg: MISSING"
have_cmd ffprobe && log "  ffprobe: OK" || log "  ffprobe: MISSING"
if have_cmd yt-dlp; then
  log "  yt-dlp: OK (PATH)"
elif [[ -x "${TOOLS}/yt-dlp" ]]; then
  log "  yt-dlp: OK (${TOOLS}/yt-dlp)"
else
  log "  yt-dlp: MISSING"
fi
if have_cmd realesrgan-ncnn-vulkan; then
  log "  realesrgan-ncnn-vulkan: OK (PATH)"
elif [[ -x "${TOOLS}/realesrgan-ncnn-vulkan" ]]; then
  log "  realesrgan-ncnn-vulkan: OK (${TOOLS}/realesrgan-ncnn-vulkan)"
else
  log "  realesrgan-ncnn-vulkan: NOT INSTALLED (required for upscaling)"
fi

if [[ "$WITH_WEB" -eq 1 ]]; then
  log ""
  log "Installing web UI dependencies..."
  PYTHON_BIN="${PYTHON:-python3}"
  if ! have_cmd "$PYTHON_BIN"; then
    log "WARNING: '$PYTHON_BIN' not found; skipping web UI install."
  else
    "$PYTHON_BIN" -m venv "${ROOT}/web/.venv"
    "${ROOT}/web/.venv/bin/pip" install --upgrade pip >/dev/null
    "${ROOT}/web/.venv/bin/pip" install -r "${ROOT}/web/requirements.txt"
    log "Web UI installed. Run with: ./web/run_server.sh"
  fi
fi

log ""
log "Done."
