#!/usr/bin/env bash
set -euo pipefail

have_cmd() { command -v "$1" >/dev/null 2>&1; }

log() { printf '%s\n' "$*"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${TOOLS_DIR:-${ROOT}/tools}"
REALESRGAN_URL="${REALESRGAN_MACOS_URL:-https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip}"
ARCHIVE_PATH="${TOOLS_DIR}/realesrgan-ncnn-vulkan-macos.zip"
EXTRACT_DIR="${TOOLS_DIR}/realesrgan-ncnn-vulkan-macos"
STABLE_BIN="${TOOLS_DIR}/realesrgan-ncnn-vulkan"

if [[ "$(uname -s)" != "Darwin" ]]; then
  log "This helper only supports macOS." >&2
  exit 1
fi

mkdir -p "${TOOLS_DIR}"

if [[ -x "${STABLE_BIN}" ]] && "${STABLE_BIN}" -h >/dev/null 2>&1; then
  log "Real-ESRGAN already installed at ${STABLE_BIN}"
  exit 0
fi

if ! have_cmd unzip; then
  log "unzip is required to extract Real-ESRGAN." >&2
  exit 1
fi

if have_cmd curl; then
  curl -fsSL -o "${ARCHIVE_PATH}" "${REALESRGAN_URL}"
elif have_cmd wget; then
  wget -q -O "${ARCHIVE_PATH}" "${REALESRGAN_URL}"
else
  log "Need curl or wget to download Real-ESRGAN." >&2
  exit 1
fi

rm -rf "${EXTRACT_DIR}"
mkdir -p "${EXTRACT_DIR}"
unzip -qo "${ARCHIVE_PATH}" -d "${EXTRACT_DIR}"

BIN_PATH="$(
  find "${EXTRACT_DIR}" -type f -name 'realesrgan-ncnn-vulkan' -print -quit
)"
if [[ -z "${BIN_PATH}" || ! -f "${BIN_PATH}" ]]; then
  log "Could not locate realesrgan-ncnn-vulkan in ${EXTRACT_DIR}" >&2
  exit 1
fi

chmod +x "${BIN_PATH}"
rm -f "${STABLE_BIN}"
cat > "${STABLE_BIN}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

REAL_BIN="${BIN_PATH}"

if [[ ! -x "\${REAL_BIN}" ]]; then
  printf 'Missing Real-ESRGAN binary at %s\n' "\${REAL_BIN}" >&2
  exit 1
fi

if [[ "\${1:-}" == "-h" ]]; then
  set +e
  "\${REAL_BIN}" "\$@"
  status=\$?
  set -e
  if [[ \${status} -eq 255 ]]; then
    exit 0
  fi
  exit \${status}
fi

exec "\${REAL_BIN}" "\$@"
EOF
chmod +x "${STABLE_BIN}"
"${STABLE_BIN}" -h >/dev/null 2>&1

log "Installed Real-ESRGAN to ${STABLE_BIN}"
