# Web Progress Feedback — Design Spec

- **Date**: 2026-05-11
- **Status**: Draft (pending user review)
- **Scope**: Improve the local web UI so running jobs show meaningful stage-local progress instead of a static `Starting...`, while keeping live thumbnail updates sampled and lightweight.

## Goal

Make the job panel communicate where the pipeline currently is, without adding a heavy new progress model. The UI should show simple stage text immediately when a stage begins, and show real numeric progress only for stages where the backend has trustworthy counts.

## Non-goals

- No overall job percentage across all stages.
- No log-parsing estimator for yt-dlp, ffmpeg, or mux progress.
- No fake or animated synthetic percentages.
- No “post every frame” behavior to the browser.
- No major visual redesign of the progress panel.

## Chosen approach

Keep the existing progress bar/text UI and improve the event flow behind it:

- show a plain stage label as soon as a stage starts
- emit real `progress` events more consistently for `extract` and `upscale`
- keep thumbnail publishing sampled and decoupled from percentage updates

### Why this approach

The frontend already knows how to render `current / total` and `%` when it receives `progress` events. The missing piece is that the backend currently emits those updates too sparsely and mostly couples them to thumbnail generation. Fixing the event cadence is the smallest reliable improvement.

## Desired behavior

### Stages without real totals

For `downloading`, `preparing`/`sync`, and `muxing`, the progress text should immediately switch away from `Starting...` and show stage text only, for example:

- `Downloading...`
- `Syncing...`
- `Muxing...`

The progress bar may remain at `0%` or reset for these stages; the important part is that the text reflects the active stage.

### Stages with real totals

For `extracting` and `upscaling`, the UI should show stage-local counts and percentage, for example:

- `Extracting 450 / 4500 (10%)`
- `Upscaling 1240 / 4500 (28%)`

These numbers should update often enough to feel alive during the run.

## Backend design

### Event model

Keep the existing event types:

- `stage`
- `progress`
- `thumbnail`
- `log`
- `complete`
- `error`

No new API shape is required for v1.

### Extract progress

After extraction completes, the backend already knows the final frame count. That is enough to publish a completion-style progress event such as:

- `current = total = frame_count`

This gives the UI a concrete extracted total before upscale begins.

### Upscale progress

During upscale, progress should be computed from the actual number of upscaled frame files present in the output directory, not from thumbnail cadence.

Recommended behavior:

- poll the upscaled frames directory on a fixed interval
- count completed `.png` files
- publish `ProgressEvent(stage="upscale", current=<count>, total=<frame_count>)` whenever the count advances

This should be independent from thumbnail publishing.

### Thumbnail sampling

Do **not** publish every frame to the browser.

Instead, continue sampling thumbnail events at a much lower cadence, roughly “a few per minute” for normal runs. The exact sampling rule does not need to be time-based if count-based sampling achieves the same user-visible effect.

The key requirement is:

- progress updates can be frequent
- thumbnail updates stay sparse

## Frontend design

### Stage text fallback

When a `stage` event with `status = started` arrives:

- mark the active stage pill as active
- update the progress text immediately to that stage label

This removes the stale `Starting...` state for long-running early stages.

Suggested text mapping:

- `downloading` -> `Downloading...`
- `preparing` -> `Syncing...`
- `extracting` -> `Extracting...`
- `upscaling` -> `Upscaling...`
- `muxing` -> `Muxing...`

### Numeric progress rendering

When a `progress` event arrives:

- compute `pct = round(current / total * 100)` when `total > 0`
- update the existing bar width
- replace the stage text with `StageLabel current / total (pct%)`

No new widget is needed beyond the existing bar and text.

## Sampling expectations

The browser should only receive sampled thumbnail images, not every generated frame.

Target UX:

- progress text moves regularly during upscale
- the thumbnail strip refreshes occasionally
- the strip remains capped to the existing small number of visible images

## Testing

Add focused coverage for both halves of the behavior:

1. frontend behavior that replaces `Starting...` with stage text when a stage starts
2. backend behavior that emits frequent-ish progress independent of thumbnail publication

The tests do not need to verify exact human-time cadence; they only need to prove:

- progress events are emitted from actual completed-frame counts
- progress emission does not depend on thumbnail emission frequency
- the UI text updates correctly for stages without totals

## Implementation notes

- This should stay a small change centered on `web/jobs.py`, `web/live_watcher.py` if needed, and `web/static/app.js`
- Prefer using the existing stage/progress event system rather than inventing a second progress channel
- Keep the solution intentionally lightweight and easy to reason about
