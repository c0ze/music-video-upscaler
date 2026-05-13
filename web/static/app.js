const $ = (sel) => document.querySelector(sel);

const THEME_KEY = "music-video-upscaler.theme";

const els = {
  themeToggle: $("#theme-toggle"),
  url: $("#url"),
  probe: $("#btn-probe"),
  probeSummary: $("#probe-summary"),
  probeError: $("#probe-error"),
  panelSettings: $("#panel-settings"),
  model: $("#model"),
  scale: $("#scale"),
  outputFormat: $("#output-format"),
  outputDir: $("#output-dir"),
  audioFile: $("#audio-file"),
  preview: $("#btn-preview"),
  run: $("#btn-run"),
  panelPreview: $("#panel-preview"),
  previewCaption: $("#preview-caption"),
  previewGrid: $("#preview-grid"),
  panelProgress: $("#panel-progress"),
  stages: document.querySelectorAll("#stages li"),
  progressBar: $("#progress-bar"),
  progressText: $("#progress-text"),
  thumbStrip: $("#thumb-strip"),
  log: $("#log"),
  cancel: $("#btn-cancel"),
  panelDone: $("#panel-done"),
  doneSummary: $("#done-summary"),
  download: $("#btn-download"),
  reveal: $("#btn-reveal"),
  newJob: $("#btn-new"),
  banner: $("#health-banner"),
};

let activeJobId = null;
let activeEventSource = null;

function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getStoredTheme() {
  const value = localStorage.getItem(THEME_KEY);
  return value === "light" || value === "dark" ? value : null;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  if (els.themeToggle) {
    els.themeToggle.textContent = theme === "dark" ? "Dark" : "Light";
    els.themeToggle.setAttribute(
      "aria-label",
      theme === "dark" ? "Theme: Dark" : "Theme: Light",
    );
  }
}

function onToggleTheme() {
  const current = document.documentElement.dataset.theme || getSystemTheme();
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

async function init() {
  applyTheme(getStoredTheme() || getSystemTheme());

  try {
    const health = await (await fetch("/api/health")).json();
    if (!health.ok) {
      els.banner.textContent =
        "Missing dependencies: " + health.missing.join(", ") +
        " — run install-dependencies.sh / install-dependencies.ps1.";
      els.banner.classList.remove("hidden");
    }
  } catch (e) {
    console.error("health check failed", e);
  }

  await loadModels();

  const stored = localStorage.getItem("activeJobId");
  if (stored) {
    try {
      const r = await fetch(`/api/jobs/${stored}`);
      if (r.ok) {
        const snap = await r.json();
        if (snap && snap.state &&
            !["complete", "failed", "cancelled"].includes(snap.state)) {
          activeJobId = stored;
          showProgressPanel();
          attachEvents(stored);
        } else {
          localStorage.removeItem("activeJobId");
        }
      } else {
        localStorage.removeItem("activeJobId");
      }
    } catch {
      localStorage.removeItem("activeJobId");
    }
  }

  els.probe.addEventListener("click", onProbe);
  els.preview.addEventListener("click", onPreview);
  els.run.addEventListener("click", onRun);
  els.cancel.addEventListener("click", onCancel);
  els.reveal.addEventListener("click", onReveal);
  els.newJob.addEventListener("click", () => location.reload());
  els.model.addEventListener("change", clearPreview);
  els.scale.addEventListener("change", clearPreview);
  if (els.themeToggle) {
    els.themeToggle.addEventListener("click", onToggleTheme);
  }
}

async function loadModels() {
  const models = await (await fetch("/api/models")).json();
  els.model.innerHTML = "";
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = m.hint ? `${m.name} — ${m.hint}` : m.name;
    if (m.default) opt.selected = true;
    els.model.appendChild(opt);
  }
}

async function onProbe() {
  els.probeError.classList.add("hidden");
  els.probeSummary.textContent = "Probing…";
  try {
    const r = await fetch("/api/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: els.url.value }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      els.probeError.textContent = err.detail || "Probe failed";
      els.probeError.classList.remove("hidden");
      els.probeSummary.textContent = "";
      return;
    }
    const meta = await r.json();
    els.probeSummary.textContent =
      `${meta.title} — ${formatDuration(meta.duration)} — ${meta.width}x${meta.height} @ ${meta.fps.toFixed(2)} fps`;
    els.scale.value = String(meta.recommended_scale);
    els.panelSettings.classList.remove("disabled");
  } catch (e) {
    els.probeError.textContent = String(e);
    els.probeError.classList.remove("hidden");
    els.probeSummary.textContent = "";
  }
}

function clearPreview() {
  els.panelPreview.classList.add("hidden");
  els.previewGrid.innerHTML = "";
}

async function onPreview() {
  clearPreview();
  const fd = new FormData();
  fd.append("url", els.url.value);
  fd.append("model", els.model.value);
  fd.append("scale", els.scale.value);
  const r = await fetch("/api/preview", { method: "POST", body: fd });
  if (!r.ok) {
    alert((await r.json().catch(() => ({}))).detail || "Preview failed");
    return;
  }
  const { job_id } = await r.json();
  els.panelPreview.classList.remove("hidden");
  els.previewCaption.textContent = `Model: ${els.model.value} • ${els.scale.value}x`;

  const es = new EventSource(`/api/jobs/${job_id}/events`);
  const seen = new Set();
  es.onmessage = (msg) => {
    let evt;
    try { evt = JSON.parse(msg.data); } catch { return; }
    if (evt.type === "thumbnail" && !seen.has(evt.frame_id + evt.kind)) {
      seen.add(evt.frame_id + evt.kind);
      addPreviewThumb(evt);
    }
    if (evt.type === "complete" || evt.type === "error") {
      es.close();
      if (evt.type === "error") alert("Preview failed: " + evt.message);
    }
  };
  es.onerror = () => {
    // Browser will retry automatically; nothing to do for v1.
  };
}

function addPreviewThumb(evt) {
  let figure = els.previewGrid.querySelector(`figure[data-frame="${evt.frame_id}"]`);
  if (!figure) {
    figure = document.createElement("figure");
    figure.dataset.frame = evt.frame_id;
    const img = document.createElement("img");
    img.alt = evt.frame_id;
    figure.appendChild(img);
    const cap = document.createElement("figcaption");
    figure.appendChild(cap);
    els.previewGrid.appendChild(figure);
  }
  const img = figure.querySelector("img");
  const cap = figure.querySelector("figcaption");
  if (evt.kind === "src") {
    figure.dataset.src = evt.url;
    cap.textContent = `Frame ${evt.frame_id} — hover to see source`;
  } else {
    figure.dataset.up = evt.url;
    img.src = evt.url;
  }
  if (figure.dataset.src && figure.dataset.up) {
    img.src = figure.dataset.up;
    figure.addEventListener("mouseenter", () => { img.src = figure.dataset.src; });
    figure.addEventListener("mouseleave", () => { img.src = figure.dataset.up; });
  }
}

async function onRun() {
  const fd = new FormData();
  fd.append("url", els.url.value);
  fd.append("model", els.model.value);
  fd.append("scale", els.scale.value);
  fd.append("output_format", els.outputFormat.value);
  if (els.outputDir.value) fd.append("output_dir", els.outputDir.value);
  if (els.audioFile.files[0]) fd.append("audio_file", els.audioFile.files[0]);

  const r = await fetch("/api/jobs", { method: "POST", body: fd });
  if (!r.ok) {
    alert((await r.json().catch(() => ({}))).detail || "Failed to start job");
    return;
  }
  const { job_id } = await r.json();
  activeJobId = job_id;
  localStorage.setItem("activeJobId", job_id);
  showProgressPanel();
  attachEvents(job_id);
}

function stageLabel(stage) {
  switch (stage) {
    case "downloading":
      return "Downloading...";
    case "preparing":
      return "Syncing...";
    case "extracting":
      return "Extracting...";
    case "upscaling":
      return "Upscaling...";
    case "muxing":
      return "Muxing...";
    default:
      return "Starting...";
  }
}

function showProgressPanel() {
  els.panelProgress.classList.remove("hidden");
  els.panelDone.classList.add("hidden");
  els.thumbStrip.innerHTML = "";
  els.log.textContent = "";
  els.progressBar.style.width = "0%";
  els.progressText.textContent = "Starting…";
  els.stages.forEach((li) => li.classList.remove("active", "done"));
}

function attachEvents(jobId) {
  if (activeEventSource) activeEventSource.close();
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  activeEventSource = es;
  es.onmessage = (msg) => {
    let evt;
    try { evt = JSON.parse(msg.data); } catch { return; }
    handleEvent(evt);
  };
  es.onerror = () => {
    // Auto-retry; if we already saw a terminal event we close above.
  };
}

function handleEvent(evt) {
  if (evt.type === "stage") {
    els.stages.forEach((li) => {
      if (li.dataset.stage === evt.stage) {
        if (evt.status === "done") {
          li.classList.remove("active");
          li.classList.add("done");
        } else {
          li.classList.add("active");
          els.progressBar.style.width = "0%";
          els.progressText.textContent = stageLabel(evt.stage);
        }
      }
    });
  }
  if (evt.type === "progress") {
    const pct = evt.total ? Math.round((evt.current / evt.total) * 100) : 0;
    const label = stageLabel(evt.stage).replace("...", "");
    els.progressBar.style.width = pct + "%";
    els.progressText.textContent = `${label} ${evt.current} / ${evt.total} (${pct}%)`;
  }
  if (evt.type === "thumbnail" && evt.kind === "up") {
    const img = document.createElement("img");
    img.src = evt.url;
    img.alt = evt.frame_id;
    els.thumbStrip.appendChild(img);
    while (els.thumbStrip.children.length > 12) {
      els.thumbStrip.removeChild(els.thumbStrip.firstChild);
    }
  }
  if (evt.type === "log") {
    els.log.textContent += evt.line + "\n";
    els.log.scrollTop = els.log.scrollHeight;
  }
  if (evt.type === "complete") {
    els.panelDone.classList.remove("hidden");
    els.doneSummary.textContent =
      `Output: ${evt.output} (${(evt.size_bytes / 1048576).toFixed(1)} MB)`;
    els.download.href = `/api/jobs/${activeJobId}/output`;
    localStorage.removeItem("activeJobId");
    if (activeEventSource) activeEventSource.close();
  }
  if (evt.type === "error") {
    alert("Job failed: " + evt.message);
    localStorage.removeItem("activeJobId");
    if (activeEventSource) activeEventSource.close();
  }
}

async function onCancel() {
  if (!activeJobId) return;
  await fetch(`/api/jobs/${activeJobId}/cancel`, { method: "POST" });
}

async function onReveal() {
  if (!activeJobId) return;
  await fetch(`/api/jobs/${activeJobId}/reveal`, { method: "POST" });
}

function formatDuration(s) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

init();
