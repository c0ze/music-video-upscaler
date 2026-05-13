# macOS Real-ESRGAN Installer — Design Spec

- **Date**: 2026-05-11
- **Status**: Draft (pending user review)
- **Scope**: Add a macOS helper that installs `realesrgan-ncnn-vulkan` into the repo-local `tools/` directory, wire that helper into `install-dependencies.sh`, and align the web health check with the pipeline's Real-ESRGAN resolution rules.

## Goal

Make the existing macOS setup path behave the way users expect: running `./install-dependencies.sh` on macOS should be able to install the required `realesrgan-ncnn-vulkan` binary automatically, and the web UI should stop reporting the dependency as missing when the pipeline can already resolve it.

## Non-goals

- No source build from ncNN / Vulkan dependencies on macOS.
- No changes to the actual upscaling stage scripts or model selection behavior.
- No Windows or Linux installer redesign beyond keeping current behavior intact.
- No attempt to package Real-ESRGAN into the Python web venv.

## Problem

The current repo already supports resolving `realesrgan-ncnn-vulkan` from multiple places at runtime, but the install and health-check flows are inconsistent:

- `lib/pipeline.sh` honors `REALESRGAN_BIN`, then `tools/realesrgan-ncnn-vulkan`, then `PATH`
- `install-dependencies.sh` can auto-download a Linux x86_64 binary, but only prints manual instructions on macOS
- `web/server.py` checks `PATH` plus repo-local tool locations, but ignores `REALESRGAN_BIN`

This produces a confusing user experience on macOS: dependency installation appears complete for most tools, but the web UI still reports Real-ESRGAN missing even when the user has a valid override path.

## Chosen approach

Add a dedicated macOS helper script and have the main installer call it automatically when needed.

### Why this approach

This is the smallest change that fixes the real problem:

- keeps platform-specific download logic isolated
- preserves the existing top-level install command users already run
- reuses the repo-local `tools/` convention already used elsewhere
- avoids a fragile source build flow on user machines
- makes health reporting match actual runtime resolution

Alternative approaches such as documenting more manual steps or only adding a standalone helper would still leave the main installer behavior surprising.

## Behavior

### Standalone helper

Add a new repo-root script:

`install-realesrgan-macos.sh`

The helper should:

1. ensure it is running on macOS
2. create `tools/` if it does not already exist
3. download the upstream macOS archive:
   `https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip`
4. extract it under a macOS-specific subdirectory inside `tools/`
5. locate the actual `realesrgan-ncnn-vulkan` executable inside the extracted payload
6. mark the executable as runnable with `chmod +x`
7. expose it at the stable repo-local path:
   `tools/realesrgan-ncnn-vulkan`
8. verify the installed binary by running:
   `tools/realesrgan-ncnn-vulkan -h`
9. exit non-zero with a clear error if any step fails

### Extraction layout

The helper should keep the extracted payload in a dedicated directory rather than scattering files directly in `tools/`.

Recommended layout:

```text
tools/
  realesrgan-ncnn-vulkan-macos.zip
  realesrgan-ncnn-vulkan-macos/
    ...upstream extracted contents...
  realesrgan-ncnn-vulkan -> tools/realesrgan-ncnn-vulkan-macos/.../realesrgan-ncnn-vulkan
```

The stable `tools/realesrgan-ncnn-vulkan` path should be the canonical repo-local entry point used by the rest of the project.

### Idempotency

The helper should be safe to re-run.

If `tools/realesrgan-ncnn-vulkan` already exists and passes the verification command, the helper may either:

- exit early with a short "already installed" message, or
- refresh the extracted payload and relink the stable path

Either behavior is acceptable as long as repeated runs do not leave the install in a worse state.

## Main installer integration

Update `install-dependencies.sh` so macOS can install Real-ESRGAN automatically without requiring a separate command.

### Required behavior on macOS

When `install-dependencies.sh` runs on macOS:

1. if `realesrgan-ncnn-vulkan` is already available on `PATH`, do nothing
2. else if `tools/realesrgan-ncnn-vulkan` already exists and is executable, do nothing
3. else invoke:
   `./install-realesrgan-macos.sh`

This keeps the helper reusable while making the main installer match user expectations.

### Required behavior on non-macOS hosts

- Linux should keep its current behavior, including the `INSTALL_REALESRGAN=1` path for Linux x86_64
- Windows guidance should remain unchanged
- non-macOS platforms must not accidentally try to download the macOS archive

## Health-check alignment

Update the web dependency health check so it matches the runtime resolution order more closely.

### Required behavior

The web health check should treat Real-ESRGAN as present if **any** of the following is true:

1. `REALESRGAN_BIN` is set and points to an executable file
2. `tools/realesrgan-ncnn-vulkan` exists and is executable
3. `windows/realesrgan-ncnn-vulkan.exe` exists and is executable
4. `realesrgan-ncnn-vulkan` is available on `PATH`

This removes the current false-negative case where the pipeline can run but the UI still reports a missing dependency.

### Resolution consistency

The web health check does not need to share literal implementation code with `lib/pipeline.sh`, but the observable behavior should stay aligned with the pipeline's supported Real-ESRGAN locations.

## Error handling

The helper script should fail clearly when prerequisites are missing or the upstream payload format changes.

Examples of failure cases that should produce readable errors:

- neither `curl` nor `wget` is available
- `unzip` is missing
- the archive downloads but extraction fails
- the expected executable cannot be found in the extracted payload
- the final `-h` verification command fails

Silent partial installs are explicitly undesirable.

## Documentation

Update user-facing docs so macOS users have one obvious install path:

```bash
./install-dependencies.sh --with-web
./web/run_server.sh
```

The docs should also mention the standalone helper for manual recovery:

```bash
./install-realesrgan-macos.sh
```

## Verification

Manual verification should confirm:

1. a fresh macOS checkout installs the binary into `tools/`
2. `./tools/realesrgan-ncnn-vulkan -h` succeeds after installation
3. rerunning `./install-dependencies.sh` does not break the existing install
4. `/api/health` no longer reports `realesrgan-ncnn-vulkan` missing after a successful helper install
5. `/api/health` also reports success when `REALESRGAN_BIN` is set to a valid executable path

## Implementation notes

- This is a tooling and health-surface change, not a pipeline behavior change.
- The helper should stay shell-only and live at repo root beside `install-dependencies.sh`.
- The design intentionally prefers a repo-local binary in `tools/` over mutating the user's global shell profile or package-manager state.
