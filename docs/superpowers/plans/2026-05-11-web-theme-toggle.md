# Web Theme Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent light/dark theme toggle to the local web UI, defaulting to system theme on first visit.

**Architecture:** Keep the change frontend-only. Add a small header control in `index.html`, extend the existing CSS-token palette in `style.css` with light/dark theme variants selected via `html[data-theme]`, and add theme bootstrap + persistence logic in `app.js` using `localStorage` and `matchMedia`.

**Tech Stack:** Static HTML, vanilla JavaScript, CSS custom properties, pytest + FastAPI static asset tests

---

### Task 1: Static surface tests for the theme toggle

**Files:**
- Modify: `web/tests/test_server_basic.py`
- Test: `web/tests/test_server_basic.py`

- [ ] **Step 1: Write the failing tests**

Add two tests:

```python
def test_index_html_contains_theme_toggle(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="theme-toggle"' in r.text
    assert 'id="theme-label"' in r.text


def test_static_js_contains_theme_bootstrap(client):
    js = client.get("/static/app.js")
    assert js.status_code == 200
    body = js.text
    assert "music-video-upscaler.theme" in body
    assert "prefers-color-scheme: dark" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `web/.venv/bin/pytest web/tests/test_server_basic.py -v`

Expected: FAIL because the toggle markup and theme bootstrap strings do not exist yet.

- [ ] **Step 3: Implement the minimal UI/bootstrap to satisfy the tests**

Do not style yet beyond what's necessary to keep the page valid. Just add the elements and JS hooks needed to satisfy the new tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `web/.venv/bin/pytest web/tests/test_server_basic.py -v`

Expected: PASS

### Task 2: Theme toggle markup + styling

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/style.css`
- Test: `web/tests/test_server_basic.py`

- [ ] **Step 1: Add header-level theme control**

Add a compact header row containing the page title plus:

```html
<div class="topbar">
  <h1>Music Video Upscaler</h1>
  <div class="theme-control">
    <span id="theme-label">Theme</span>
    <button id="theme-toggle" type="button" aria-labelledby="theme-label">
      Dark
    </button>
  </div>
</div>
```

- [ ] **Step 2: Add theme-aware CSS tokens**

Extend `style.css` so:

```css
:root {
  color-scheme: light dark;
  /* defaults may remain dark-compatible */
}

html[data-theme="dark"] {
  color-scheme: dark;
  /* dark tokens */
}

html[data-theme="light"] {
  color-scheme: light;
  /* light tokens */
}
```

Cover all existing surfaces that currently use hard-coded dark colors:
- page background
- panel background
- inputs/selects
- buttons
- stage pills
- progress track
- preview cards
- log surface
- banner surface

- [ ] **Step 3: Style the new header/toggle**

Add only the minimum new selectors needed:

```css
.topbar { ... }
.theme-control { ... }
#theme-label { ... }
#theme-toggle { ... }
```

Keep it compact, keyboard-visible, and aligned with the existing UI.

- [ ] **Step 4: Run the static tests again**

Run: `web/.venv/bin/pytest web/tests/test_server_basic.py -v`

Expected: PASS

### Task 3: Theme bootstrap + persistence logic

**Files:**
- Modify: `web/static/app.js`
- Test: `web/tests/test_server_basic.py`

- [ ] **Step 1: Add theme constants + helpers**

Add:

```javascript
const THEME_KEY = "music-video-upscaler.theme";

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
    els.themeToggle.setAttribute("aria-label", `Theme: ${theme}`);
  }
}
```

- [ ] **Step 2: Bootstrap theme on first init**

Before the rest of `init()` performs app setup, resolve:

```javascript
applyTheme(getStoredTheme() || getSystemTheme());
```

- [ ] **Step 3: Add toggle click handler**

Wire the button so clicking it flips between explicit `light` and `dark`, saves to `localStorage`, and reapplies immediately:

```javascript
function onToggleTheme() {
  const current = document.documentElement.dataset.theme || getSystemTheme();
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}
```

- [ ] **Step 4: Register the event listener**

Add the toggle element to `els` and register:

```javascript
els.themeToggle.addEventListener("click", onToggleTheme);
```

- [ ] **Step 5: Run the static tests**

Run: `web/.venv/bin/pytest web/tests/test_server_basic.py -v`

Expected: PASS

### Task 4: Regression verification

**Files:**
- Modify: none
- Test: `web/tests`

- [ ] **Step 1: Run the full web suite**

Run: `web/.venv/bin/pytest web/tests -q`

Expected: all tests pass

- [ ] **Step 2: Sanity-check the page manually**

Run:

```bash
./web/run_server.sh
```

Then verify:
- the page follows system theme on first visit
- clicking the toggle switches theme immediately
- reloading preserves the explicit theme choice

