# Manual smoke test — web UI

Use a real, public, short YouTube music video (≤ 2 minutes) you don't mind
re-running. The full upscale will take several minutes even at 240p — that's
expected.

## Setup
1. `./install-dependencies.sh --with-web` (or `windows\install-dependencies.ps1 -WithWeb`).
2. `./web/run_server.sh` (or `web\run_server.ps1`).
3. Open `http://127.0.0.1:8765/` in a browser.

## Health & probe
- [ ] No red banner. (If yes, fix missing deps and retry.)
- [ ] Model dropdown lists at least `realesr-general-x4v3`, default selected.
- [ ] Paste URL, click **Probe**. Summary appears with title, duration, resolution, fps.
- [ ] Scale auto-selects (`2x` for 1080p+, `4x` otherwise).

## Preview
- [ ] Click **Preview**. After ~30s, 5 thumbnails appear.
- [ ] Hover swaps src ↔ upscaled in each thumbnail.
- [ ] Change model and re-preview; old thumbnails clear before the new set arrives.

## Full run
- [ ] Click **Run**. Stage indicator advances:
      Downloading → Sync → Extract → Upscale → Mux.
- [ ] During Upscale, thumbnails stream into the strip in roughly frame order.
- [ ] Refresh the browser mid-Upscale; UI reattaches and resumes from the
      current state (no "job not found", no duplicate progress).
- [ ] Click **Cancel** during a run. Job state becomes `cancelled` within ~10s
      and the stage strip stops advancing.

## Completion
- [ ] Run a fresh job to completion. Done panel shows the output path + size.
- [ ] **Download** returns the file (browser starts a download of the muxed video).
- [ ] **Reveal in file manager** opens the containing folder
      (Finder on macOS, Explorer on Windows, default file manager on Linux).
- [ ] **New job** resets the form to its initial state.

## Cleanup expectations
- [ ] Restarting the server prunes terminal job workdirs older than 7 days while
      keeping the 5 most recent and any non-terminal jobs.
