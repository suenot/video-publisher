# video_youtube_publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Camoufox-driven tool that publishes a finished video to YouTube (Studio UI, no Data API), with channel selection, a length/verified pre-check, and post-upload result verification.

**Architecture:** Pure logic (metadata, pre-check math, gate-text detection, result-status parsing, secret audit) lives in small unit-tested modules. Browser orchestration (`camoufox_session.py`, `channel.py`, browser parts of `publish.py`, `login.py`) is thin glue over those modules and is verified manually against live Studio. Everything runs on one persistent Camoufox profile logged into a dedicated Google account.

**Tech Stack:** Python 3.11–3.13, Camoufox + Playwright (async), ffmpeg/ffprobe, pytest (dev), gh CLI.

## Global Constraints

- Python interpreter: 3.11, 3.12, or 3.13 — NOT 3.14 (Camoufox 0.4.11 needs Playwright ≤ 1.51).
- Default visibility: `private`. Public only when `--visibility public` is passed explicitly.
- Public GitHub repo. NEVER commit: `.camoufox_profile/`, `.camoufox_fp.pkl`, `debug/`, `output/`, `input/`, `*.log`, `*.sqlite`, `cookies*.json`. No account emails / channel IDs / tokens hardcoded in source.
- YouTube limits copied verbatim: title ≤ 100 chars; tags total ≤ 500 chars (we cap at 480); unverified channels reject videos > 15 minutes (900 s).
- Audience default: "Not made for kids".
- Exit codes: `0` ok · `2` bad args · `3` not logged in · `4` couldn't start upload · `5` details failed · `6` couldn't finish/verify · `7` blocked by "Verify it's you" · `8` pre-check failed.
- Camoufox launch mirrors gaia: persistent context, pinned fingerprint, `geoip` guarded, visible window (headless less reliable with Google).

---

## File Structure

```
video_youtube_publish/
├── README.md
├── requirements.txt
├── .gitignore                     # exists from spec commit
├── .githooks/pre-commit
├── metadata.py                    # pure: load/merge/cap metadata
├── precheck.py                    # ffprobe duration + check() logic
├── youtube_ui.py                  # shadow-DOM helpers + verify_gate_present
├── verify_result.py               # parse post-upload status
├── channel.py                     # resolve + switch active channel
├── camoufox_session.py            # persistent Camoufox launch
├── login.py                       # one-time manual sign-in
├── publish.py                     # CLI orchestrator
├── scripts/audit_secrets.sh       # pre-push leak audit
└── tests/
    ├── test_metadata.py
    ├── test_precheck.py
    ├── test_youtube_ui.py
    ├── test_verify_result.py
    └── test_channel.py
```

---

### Task 1: Project scaffold + secret guards

**Files:**
- Create: `requirements.txt`, `.githooks/pre-commit`, `scripts/audit_secrets.sh`, `README.md`
- Verify: `.gitignore` (already committed) covers all secret patterns

**Interfaces:**
- Produces: `scripts/audit_secrets.sh` exiting non-zero if any tracked file matches secret patterns; a pre-commit hook blocking staged secrets.

- [ ] **Step 1: Write `requirements.txt`**

```
camoufox[geoip]==0.4.11
playwright>=1.49,<=1.51
pytest>=8.0
pytest-asyncio>=0.24
```

- [ ] **Step 2: Write `scripts/audit_secrets.sh`**

```bash
#!/usr/bin/env bash
# Fail if any tracked (or staged) file looks like a session secret.
set -euo pipefail
PATTERN='(^|/)\.camoufox_profile/|\.camoufox_fp\.pkl$|\.sqlite$|cookies.*\.json$|^debug/'
hits="$(git ls-files | grep -E "$PATTERN" || true)"
staged="$(git diff --cached --name-only | grep -E "$PATTERN" || true)"
if [[ -n "$hits$staged" ]]; then
  echo "SECRET LEAK BLOCKED — these must never be committed:" >&2
  printf '%s\n' "$hits" "$staged" | sed '/^$/d' >&2
  exit 1
fi
echo "secret audit clean"
```

- [ ] **Step 3: Write `.githooks/pre-commit`**

```bash
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/audit_secrets.sh"
```

- [ ] **Step 4: Make hooks executable and enable them**

Run:
```bash
chmod +x scripts/audit_secrets.sh .githooks/pre-commit
git config core.hooksPath .githooks
```

- [ ] **Step 5: Verify the guard blocks a secret**

Run:
```bash
mkdir -p .camoufox_profile && echo x > .camoufox_profile/cookies.sqlite
git add -f .camoufox_profile/cookies.sqlite 2>/dev/null; bash scripts/audit_secrets.sh; echo "exit=$?"
git reset -q; rm -rf .camoufox_profile
```
Expected: prints "SECRET LEAK BLOCKED" and `exit=1`.

- [ ] **Step 6: Write `README.md`** with: purpose, ⚠️ account-safety warning (the profile grants full account access — never commit it), setup (`python3.11 -m venv venv`, `pip install -r requirements.txt`, `python3 -m camoufox fetch`, `python3 login.py`), usage examples for `publish.py`, and exit-code table (copy from Global Constraints).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt scripts/audit_secrets.sh .githooks/pre-commit README.md
git commit -m "chore: scaffold + secret-leak guards"
```

---

### Task 2: `metadata.py` (pure)

**Files:**
- Create: `metadata.py`, `tests/test_metadata.py`

**Interfaces:**
- Produces:
  - `cap_tags(tags: list[str], budget: int = 480) -> list[str]`
  - `load_metadata(metadata_path: str|None, title: str, description: str, tags_csv: str) -> dict` returning `{"title": str, "description": str, "tags": list[str]}`; reads a video_maker JSON (`{title, description, tags[]}`) when `metadata_path` is given; CLI args override; title truncated to 100 chars; tags capped via `cap_tags`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_metadata.py
import json
from metadata import cap_tags, load_metadata

def test_cap_tags_stops_before_budget():
    assert cap_tags(["aaaa", "bbbb", "cccc"], budget=9) == ["aaaa"]  # 4 + 1 + 4 = 9 > 9 stops

def test_cap_tags_keeps_all_when_under_budget():
    assert cap_tags(["a", "b"], budget=480) == ["a", "b"]

def test_load_metadata_from_json(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"title": "T", "description": "D", "tags": ["x", "y"]}))
    m = load_metadata(str(p), "", "", "")
    assert m == {"title": "T", "description": "D", "tags": ["x", "y"]}

def test_cli_overrides_and_title_truncation(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"title": "old", "description": "D", "tags": ["x"]}))
    long = "z" * 130
    m = load_metadata(str(p), long, "", "a, b ,")
    assert len(m["title"]) == 100
    assert m["tags"] == ["a", "b"]
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_metadata.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'metadata'`).

- [ ] **Step 3: Implement `metadata.py`**

```python
import json
from pathlib import Path


def cap_tags(tags, budget=480):
    out, used = [], 0
    for t in tags:
        add = len(t) + (1 if out else 0)
        if used + add > budget:
            break
        out.append(t)
        used += add
    return out


def load_metadata(metadata_path, title, description, tags_csv):
    meta = {"title": "", "description": "", "tags": []}
    if metadata_path:
        p = Path(metadata_path).expanduser()
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            meta["title"] = (data.get("title") or "").strip()
            meta["description"] = data.get("description") or ""
            meta["tags"] = [t for t in (data.get("tags") or []) if t]
    if title:
        meta["title"] = title
    if description:
        meta["description"] = description
    if tags_csv:
        meta["tags"] = [t.strip() for t in tags_csv.split(",") if t.strip()]
    meta["title"] = meta["title"][:100]
    meta["tags"] = cap_tags(meta["tags"])
    return meta
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_metadata.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add metadata.py tests/test_metadata.py
git commit -m "feat: metadata merge/cap (pure, tested)"
```

---

### Task 3: `precheck.py` (duration + gate logic)

**Files:**
- Create: `precheck.py`, `tests/test_precheck.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `parse_ffprobe_duration(stdout: str) -> float` (seconds from ffprobe's plain `format=duration` output).
  - `video_duration(path: str, runner=<subprocess>) -> float` (calls ffprobe; `runner` injectable for tests, returns stdout string).
  - `check(duration_s: float, verified: bool, allow_long: bool) -> tuple[bool, str]` — returns `(False, reason)` when `duration_s > 900 and not verified and not allow_long`, else `(True, "")`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_precheck.py
from precheck import parse_ffprobe_duration, video_duration, check

def test_parse_duration():
    assert parse_ffprobe_duration("2618.53\n") == 2618.53

def test_video_duration_uses_runner():
    assert video_duration("x.mp4", runner=lambda path: "12.0\n") == 12.0

def test_check_blocks_long_unverified():
    ok, reason = check(2618.0, verified=False, allow_long=False)
    assert ok is False and "too long" in reason.lower()

def test_check_allows_short():
    assert check(600.0, verified=False, allow_long=False) == (True, "")

def test_check_allows_long_when_verified():
    assert check(2618.0, verified=True, allow_long=False) == (True, "")

def test_check_allows_long_with_override():
    assert check(2618.0, verified=False, allow_long=True) == (True, "")
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_precheck.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'precheck'`).

- [ ] **Step 3: Implement `precheck.py`**

```python
import subprocess

LIMIT_S = 900  # 15 min, the unverified-channel ceiling


def parse_ffprobe_duration(stdout):
    return float(stdout.strip())


def _default_runner(path):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", path],
        capture_output=True, text=True, check=True).stdout


def video_duration(path, runner=_default_runner):
    return parse_ffprobe_duration(runner(path))


def check(duration_s, verified, allow_long):
    if duration_s > LIMIT_S and not verified and not allow_long:
        return (False, f"Video is {int(duration_s)}s (> {LIMIT_S}s / 15min) and the "
                       "channel is not verified — YouTube will abandon processing. "
                       "Verify the channel (youtube.com/verify) or pass --allow-long.")
    return (True, "")
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_precheck.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add precheck.py tests/test_precheck.py
git commit -m "feat: precheck duration + long/unverified gate (tested)"
```

---

### Task 4: `verify_result.py` (status parse, pure)

**Files:**
- Create: `verify_result.py`, `tests/test_verify_result.py`

**Interfaces:**
- Produces: `parse_status(page_text: str, title: str) -> tuple[str, str]` returning `(status, note)` where status ∈ {`"failed"`, `"processing"`, `"present"`, `"absent"`}. Rules (checked in order): title not in text → `("absent", "")`; text contains "processing abandoned" or "too long" → `("failed", <the matched phrase>)`; contains "processing" or "checking" → `("processing", "")`; else `("present", "")`. Matching is case-insensitive.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_verify_result.py
from verify_result import parse_status

T = "Building a Market Making Algorithm"

def test_absent_when_title_missing():
    assert parse_status("some other content", T) == ("absent", "")

def test_failed_on_abandoned():
    txt = f"{T} | Processing abandoned Video is too long"
    status, note = parse_status(txt, T)
    assert status == "failed" and "too long" in note.lower()

def test_processing():
    assert parse_status(f"{T} | Checking...", T) == ("processing", "")

def test_present():
    assert parse_status(f"{T} | Private | 0 views", T) == ("present", "")
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_verify_result.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `verify_result.py`**

```python
def parse_status(page_text, title):
    low = page_text.lower()
    if title.lower() not in low:
        return ("absent", "")
    for phrase in ("processing abandoned", "too long"):
        if phrase in low:
            return ("failed", phrase)
    for phrase in ("processing", "checking"):
        if phrase in low:
            return ("processing", "")
    return ("present", "")
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_verify_result.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add verify_result.py tests/test_verify_result.py
git commit -m "feat: post-upload status parse (tested)"
```

---

### Task 5: `youtube_ui.py` (shadow-DOM helpers)

**Files:**
- Create: `youtube_ui.py`, `tests/test_youtube_ui.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all `async` except the JS constants):
  - `JS_ALL_TEXT: str`, `JS_DEEP_DUMP: str` (shadow-piercing JS).
  - `async verify_gate_present(page) -> bool` — evaluates `JS_ALL_TEXT`, True if it contains "verify it's you" / "confirm it's really you" (straight and curly apostrophes).
  - `async all_text(page) -> str`
  - `async click_text(page, words: list[str], timeout_ms=4000) -> bool`
  - `async fill_contenteditable(page, loc, text) -> bool`
  - `async first_present(page, selectors: list[str], timeout_ms=15000)` (returns a locator or None; matches on existence, not visibility — YouTube file inputs are hidden)
  - `async dismiss_overlays(page) -> None`
- The `page`/`loc` objects are duck-typed; tests pass fakes exposing the awaited methods used.

- [ ] **Step 1: Write failing tests** (fake async page for the pure-ish helpers)

```python
# tests/test_youtube_ui.py
import pytest
from youtube_ui import verify_gate_present, all_text

class FakePage:
    def __init__(self, text): self._text = text
    async def evaluate(self, js): return self._text

@pytest.mark.asyncio
async def test_all_text_returns_evaluate():
    assert await all_text(FakePage("hello")) == "hello"

@pytest.mark.asyncio
async def test_gate_detected_straight_apostrophe():
    assert await verify_gate_present(FakePage("please verify it's you now")) is True

@pytest.mark.asyncio
async def test_gate_detected_curly_apostrophe():
    assert await verify_gate_present(FakePage("verify it’s you")) is True

@pytest.mark.asyncio
async def test_gate_absent():
    assert await verify_gate_present(FakePage("channel dashboard")) is False
```

Add `tests/conftest.py`:
```python
# tests/conftest.py — nothing needed beyond asyncio_mode
```
And create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_youtube_ui.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'youtube_ui'`).

- [ ] **Step 3: Implement `youtube_ui.py`**

```python
import time

JS_ALL_TEXT = r"""
() => {
  const acc=[]; const seen=new Set();
  function walk(root){
    if(!root||seen.has(root))return; seen.add(root);
    for(const n of (root.childNodes||[])){
      if(n.nodeType===3){const t=(n.textContent||'').trim(); if(t)acc.push(t);}
      else if(n.nodeType===1){ if(n.shadowRoot) walk(n.shadowRoot); walk(n); }
    }
  }
  walk(document.body); return acc.join(' ').toLowerCase();
}
"""

JS_DEEP_DUMP = r"""
() => {
  const out=[]; const seen=new Set();
  function walk(root){
    let els; try{els=root.querySelectorAll('*')}catch(e){return}
    for(const el of els){
      if(seen.has(el))continue; seen.add(el);
      const tag=el.tagName.toLowerCase();
      const aria=el.getAttribute&&el.getAttribute('aria-label');
      const id=el.id||''; const nm=el.getAttribute&&el.getAttribute('name');
      const role=el.getAttribute&&el.getAttribute('role');
      const ok=['button','input','textarea','a','tp-yt-paper-item',
        'tp-yt-paper-radio-button','ytcp-button'].includes(tag)||aria||role==='radio';
      if(ok){const r=el.getBoundingClientRect?el.getBoundingClientRect():{width:0,height:0,x:0,y:0};
        if(r.width>0&&r.height>0)
          out.push({tag,id,name:nm||'',role:role||'',aria:(aria||'').slice(0,50),
            text:(el.innerText||el.textContent||'').trim().slice(0,40),
            x:Math.round(r.x),y:Math.round(r.y)});}
      if(el.shadowRoot)walk(el.shadowRoot);
    }
  }
  walk(document); return out;
}
"""


async def all_text(page):
    try:
        return await page.evaluate(JS_ALL_TEXT)
    except Exception:
        return ""


async def verify_gate_present(page):
    t = await all_text(page)
    return ("verify it's you" in t or "verify it’s you" in t
            or "confirm it's really you" in t or "confirm it’s really you" in t)


async def click_text(page, words, timeout_ms=4000):
    sel = ("button, [role=button], [role=menuitem], [role=radio], "
           "tp-yt-paper-item, ytcp-button, a")
    try:
        await page.wait_for_selector(sel, timeout=timeout_ms)
    except Exception:
        pass
    loc = page.locator(sel)
    n = await loc.count()
    for i in range(n):
        el = loc.nth(i)
        try:
            if not await el.is_visible():
                continue
            hay = ((await el.get_attribute("aria-label") or "") + " "
                   + (await el.inner_text() or "")).lower()
            if any(w.lower() in hay for w in words):
                await el.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


async def fill_contenteditable(page, loc, text):
    try:
        await loc.click(timeout=4000)
        await page.wait_for_timeout(200)
        for combo in ("Meta+A", "Control+A"):
            try:
                await page.keyboard.press(combo)
            except Exception:
                pass
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(150)
        await page.keyboard.type(text, delay=2)
        await page.wait_for_timeout(300)
        return True
    except Exception:
        return False


async def first_present(page, selectors, timeout_ms=15000):
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if await loc.count() > 0:
                    return loc.first
            except Exception:
                continue
        await page.wait_for_timeout(500)
    return None


async def dismiss_overlays(page):
    for txt in ("Got it", "Dismiss", "No thanks", "Skip", "Not now",
                "Continue", "I agree", "Accept all"):
        try:
            b = page.locator(f"ytcp-button:has-text('{txt}'), button:has-text('{txt}')")
            if await b.count() > 0 and await b.first.is_visible():
                await b.first.click(timeout=1500)
                await page.wait_for_timeout(400)
        except Exception:
            continue
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_youtube_ui.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add youtube_ui.py tests/test_youtube_ui.py tests/conftest.py pytest.ini
git commit -m "feat: shadow-DOM UI helpers + verify-gate detection (tested)"
```

---

### Task 6: `camoufox_session.py` (browser launch)

**Files:**
- Create: `camoufox_session.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `make_camoufox(headless: bool = False)` → AsyncCamoufox persistent context manager (own `.camoufox_profile/` + pinned fingerprint file `.camoufox_fp.pkl`).
  - `async prepare_page(context) -> page`
  - `async logged_in_youtube(page) -> bool` (has an `SID`/`__Secure-1PSID` cookie for `.youtube.com`).
  - `log(msg)`, `async shot(page, name, enabled)` writing to `debug/`.

- [ ] **Step 1: Implement `camoufox_session.py`** (adapted from gaia `gemini_common`, trimmed to YouTube)

```python
import pickle
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / ".camoufox_profile"
FP_FILE = HERE / ".camoufox_fp.pkl"
DEBUG_DIR = HERE / "debug"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _geoip_available():
    try:
        import socket
        socket.create_connection(("api.ipify.org", 443), timeout=3).close()
        return True
    except Exception:
        return False


def _stable_fingerprint():
    if FP_FILE.exists():
        try:
            return pickle.loads(FP_FILE.read_bytes())
        except Exception:
            return None
    return None


def make_camoufox(headless=False):
    from camoufox.async_api import AsyncCamoufox
    PROFILE_DIR.mkdir(exist_ok=True)
    opts = dict(headless=headless, humanize=True, geoip=_geoip_available(),
                block_images=False, persistent_context=True,
                user_data_dir=str(PROFILE_DIR), window=(1440, 900))
    fp = _stable_fingerprint()
    if fp is not None:
        opts["fingerprint"] = fp
    else:
        opts["os"] = "macos"
    return AsyncCamoufox(**opts)


async def prepare_page(context):
    return context.pages[0] if context.pages else await context.new_page()


async def logged_in_youtube(page):
    try:
        cks = await page.context.cookies("https://www.youtube.com")
        return any(c["name"] in ("__Secure-1PSID", "SID") for c in cks)
    except Exception:
        return False


async def shot(page, name, enabled=True):
    if not enabled:
        return
    DEBUG_DIR.mkdir(exist_ok=True)
    try:
        await page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=False)
        log(f"  screenshot -> debug/{name}.png")
    except Exception as e:
        log(f"  (screenshot {name} failed: {e})")
```

- [ ] **Step 2: Manual verify — import + launch smoke**

Run:
```bash
venv/bin/python -c "import camoufox_session as s; print('import ok')"
```
Expected: `import ok` (no launch yet — launch is exercised in Task 8/9).

- [ ] **Step 3: Commit**

```bash
git add camoufox_session.py
git commit -m "feat: standalone Camoufox session (own profile/fingerprint)"
```

---

### Task 7: `channel.py` (resolve + switch active channel)

**Files:**
- Create: `channel.py`, `tests/test_channel.py`

**Interfaces:**
- Consumes: `camoufox_session.log`, `youtube_ui.all_text`.
- Produces:
  - `normalize_handle(handle: str) -> str` (ensure leading `@`, strip URL/whitespace) — pure.
  - `channel_id_from_url(url: str) -> str|None` (extract `UC...` from a Studio URL) — pure.
  - `async select_channel(page, channel_id: str|None, handle: str|None) -> str|None` — navigates Studio to the target channel and returns the active channel id it landed on (browser; verified manually).

- [ ] **Step 1: Write failing tests (pure helpers only)**

```python
# tests/test_channel.py
from channel import normalize_handle, channel_id_from_url

def test_normalize_handle_adds_at():
    assert normalize_handle("marketmaker-cc") == "@marketmaker-cc"

def test_normalize_handle_from_url():
    assert normalize_handle("https://youtube.com/@marketmaker-cc") == "@marketmaker-cc"

def test_channel_id_from_url():
    u = "https://studio.youtube.com/channel/UCbPEVsO_M-axL0mylsoTADw/videos"
    assert channel_id_from_url(u) == "UCbPEVsO_M-axL0mylsoTADw"

def test_channel_id_from_url_none():
    assert channel_id_from_url("https://studio.youtube.com/") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_channel.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `channel.py`**

```python
import re
from camoufox_session import log

STUDIO = "https://studio.youtube.com"


def normalize_handle(handle):
    h = handle.strip().rstrip("/")
    h = h.split("/")[-1]
    if not h.startswith("@"):
        h = "@" + h
    return h


def channel_id_from_url(url):
    m = re.search(r"/channel/(UC[\w-]+)", url or "")
    return m.group(1) if m else None


async def select_channel(page, channel_id=None, handle=None):
    target = channel_id
    if not target and handle:
        h = normalize_handle(handle)
        await page.goto(f"https://www.youtube.com/{h}",
                        wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)
        html = await page.content()
        m = re.search(r'"channelId":"(UC[\w-]+)"', html)
        target = m.group(1) if m else None
        if not target:
            log(f"  could not resolve handle {h} to a channel id")
            return None
    if target:
        await page.goto(f"{STUDIO}/channel/{target}",
                        wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(4000)
    active = channel_id_from_url(page.url)
    if target and active != target:
        log(f"  WARNING: asked for {target} but active channel is {active} "
            "(account may not own it)")
    else:
        log(f"  active channel: {active}")
    return active
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_channel.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add channel.py tests/test_channel.py
git commit -m "feat: channel resolve + switch (pure helpers tested)"
```

---

### Task 8: `publish.py` (CLI orchestrator)

**Files:**
- Create: `publish.py`
- Test: `tests/test_publish_args.py`

**Interfaces:**
- Consumes: `metadata.load_metadata`, `precheck.{video_duration,check}`, `youtube_ui.*`, `channel.select_channel`, `verify_result.parse_status`, `camoufox_session.{make_camoufox,prepare_page,logged_in_youtube,log,shot}`.
- Produces: `parse_args(argv) -> argparse.Namespace`; `async run(args) -> int` (the flow); `main(argv=None) -> int`.

- [ ] **Step 1: Write failing test for arg parsing**

```python
# tests/test_publish_args.py
from publish import parse_args

def test_defaults():
    a = parse_args(["--video", "v.mp4"])
    assert a.visibility == "private" and a.made_for_kids is False and a.allow_long is False

def test_channel_and_visibility():
    a = parse_args(["--video", "v.mp4", "--channel-handle", "@x", "--visibility", "public"])
    assert a.channel_handle == "@x" and a.visibility == "public"
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_publish_args.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'publish'`).

- [ ] **Step 3: Implement `publish.py`**

```python
import argparse
import asyncio
import sys
import time
from pathlib import Path

from camoufox_session import make_camoufox, prepare_page, logged_in_youtube, log, shot
from metadata import load_metadata
from precheck import video_duration, check
from channel import select_channel
from verify_result import parse_status
import youtube_ui as ui

STUDIO = "https://studio.youtube.com"


async def _goto(page, url, tries=3):
    last = None
    for _ in range(tries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            return
        except Exception as e:
            last = e
            await page.wait_for_timeout(1500)
    if last:
        raise last


async def open_upload(page, video, debug):
    await ui.dismiss_overlays(page)
    for sel in ("ytcp-icon-button#upload-icon", "ytcp-button#upload-button",
                "button[aria-label='Upload videos']"):
        loc = page.locator(sel)
        try:
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=4000)
                break
        except Exception:
            continue
    else:
        await ui.click_text(page, ["Create"], 8000)
        await page.wait_for_timeout(800)
        await ui.click_text(page, ["Upload video"], 5000)
    await page.wait_for_timeout(1500)
    await ui.dismiss_overlays(page)
    await shot(page, "yt_02_upload_dialog", debug)
    fi = await ui.first_present(
        page, ["ytcp-uploads-dialog input[type='file']", "input[type='file']"], 15000)
    if fi is None:
        log("  no file input found")
        return False
    await fi.set_input_files(str(video))
    log(f"  selected: {video.name}")
    await page.wait_for_timeout(4000)
    return True


async def fill_details(page, meta, thumbnail, made_for_kids, debug):
    tb = await ui.first_present(page, ["#title-textarea #textbox"], 30000)
    if tb is not None and meta["title"]:
        await ui.fill_contenteditable(page, tb, meta["title"])
        log("  title set")
    db = await ui.first_present(page, ["#description-textarea #textbox"], 5000)
    if db is not None and meta["description"]:
        await ui.fill_contenteditable(page, db, meta["description"])
        log("  description set")
    if thumbnail and Path(thumbnail).is_file():
        th = page.locator("ytcp-thumbnails-compact-editor-uploader input[type='file'], "
                          "#file-loader input[type='file']")
        try:
            if await th.count() > 0:
                await th.first.set_input_files(str(thumbnail))
                log("  thumbnail set")
                await page.wait_for_timeout(2000)
            else:
                log("  thumbnail input not ready; skipping")
        except Exception:
            log("  thumbnail failed; skipping")
    if meta["tags"]:
        await ui.click_text(page, ["Show more"], 4000)
        await page.wait_for_timeout(800)
        ti = await ui.first_present(page, ["input[aria-label='Tags']",
                                           "#tags-container input#text-input"], 4000)
        if ti is not None:
            await ti.click(timeout=3000)
            await page.keyboard.type(", ".join(meta["tags"]) + ",", delay=2)
            log("  tags set")
    name = ("VIDEO_MADE_FOR_KIDS_MFK" if made_for_kids
            else "VIDEO_MADE_FOR_KIDS_NOT_MFK")
    r = page.locator(f"tp-yt-paper-radio-button[name='{name}']")
    try:
        if await r.count() > 0:
            await r.first.click(timeout=4000)
            log("  audience set")
    except Exception:
        pass
    await shot(page, "yt_05_details", debug)


async def click_next(page, times, debug):
    for i in range(times):
        nx = page.locator("ytcp-button#next-button, #next-button")
        try:
            if await nx.count() > 0 and await nx.first.is_visible():
                await nx.first.click(timeout=5000)
                await page.wait_for_timeout(1500)
        except Exception:
            pass


async def set_visibility(page, visibility, debug):
    name = {"private": "PRIVATE", "unlisted": "UNLISTED",
            "public": "PUBLIC"}.get(visibility, "PRIVATE")
    r = page.locator(f"tp-yt-paper-radio-button[name='{name}']")
    try:
        if await r.count() > 0:
            await r.first.click(timeout=5000)
            log(f"  visibility: {visibility}")
    except Exception:
        pass
    await shot(page, "yt_07_visibility", debug)


async def save(page, debug):
    d = page.locator("ytcp-button#done-button, #done-button")
    try:
        if await d.count() > 0 and await d.first.is_visible():
            await d.first.click(timeout=6000)
            log("  clicked Save")
    except Exception:
        pass
    await page.wait_for_timeout(4000)
    await shot(page, "yt_08_saved", debug)


async def run(args):
    video = Path(args.video).expanduser()
    if not video.is_file():
        log(f"ERROR: --video not found: {video}")
        return 2
    meta = load_metadata(args.metadata, args.title, args.description, args.tags)
    if not meta["title"]:
        meta["title"] = video.stem.replace("-", " ").replace("_", " ").title()

    async with make_camoufox(args.headless) as ctx:
        page = await prepare_page(ctx)
        page.on("dialog", lambda d: asyncio.create_task(d.accept()))
        await _goto(page, STUDIO)
        await page.wait_for_timeout(4000)
        await shot(page, "yt_01_studio", args.debug)
        if not await logged_in_youtube(page):
            log("ERROR: not logged in. Run login.py first.")
            return 3

        if await ui.verify_gate_present(page):
            log("BLOCKED: 'Verify it's you' challenge.")
            await shot(page, "yt_verify_gate", True)
            if not args.keep_open:
                log("  Re-run with --keep-open and clear it in the window.")
                return 7
            log(f"  Complete it in the window; waiting up to {args.verify_wait}s...")
            await ui.click_text(page, ["Next", "Continue"], 4000)
            end = time.time() + args.verify_wait
            while time.time() < end and await ui.verify_gate_present(page):
                await page.wait_for_timeout(3000)
            if await ui.verify_gate_present(page):
                log("  still gated; aborting.")
                return 7
            await _goto(page, STUDIO)
            await page.wait_for_timeout(3000)

        if args.channel_id or args.channel_handle:
            await select_channel(page, args.channel_id, args.channel_handle)

        verified = False  # conservative default; long videos need --allow-long
        dur = video_duration(str(video))
        ok, reason = check(dur, verified, args.allow_long)
        if not ok:
            log(f"PRECHECK FAILED: {reason}")
            return 8
        log(f"  duration {int(dur)}s ok")

        if not await open_upload(page, video, args.debug):
            return 4
        await fill_details(page, meta, args.thumbnail, args.made_for_kids, args.debug)
        await click_next(page, 3, args.debug)
        await set_visibility(page, args.visibility, args.debug)
        await save(page, args.debug)

        # Verify result on the Content list.
        active = None
        try:
            from channel import channel_id_from_url
            active = channel_id_from_url(page.url)
        except Exception:
            pass
        if active:
            await _goto(page, f"{STUDIO}/channel/{active}/videos/upload")
            await page.wait_for_timeout(5000)
        text = await ui.all_text(page)
        status, note = parse_status(text, meta["title"])
        log(f"RESULT: status={status} note={note}")
        if args.keep_open:
            log("--keep-open: browser stays open. Ctrl+C to quit.")
            while True:
                await page.wait_for_timeout(3600_000)
        return 0 if status in ("present", "processing") else 6


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Publish a video to YouTube via Camoufox.")
    p.add_argument("--video", required=True)
    p.add_argument("--metadata", default="")
    p.add_argument("--thumbnail", default="")
    p.add_argument("--title", default="")
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--channel-id", default="")
    p.add_argument("--channel-handle", default="")
    p.add_argument("--visibility", default="private",
                   choices=["private", "unlisted", "public"])
    p.add_argument("--made-for-kids", action="store_true")
    p.add_argument("--allow-long", action="store_true")
    p.add_argument("--verify-wait", type=int, default=600)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run arg test to verify pass**

Run: `venv/bin/pytest tests/test_publish_args.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run full unit suite**

Run: `venv/bin/pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add publish.py tests/test_publish_args.py
git commit -m "feat: publish.py orchestrator + CLI (arg tests)"
```

---

### Task 9: `login.py` + live end-to-end verify

**Files:**
- Create: `login.py`

**Interfaces:**
- Consumes: `camoufox_session.{make_camoufox,prepare_page,logged_in_youtube,log}`.
- Produces: a script that opens Studio and holds the window open until the user has signed in (polls `logged_in_youtube`).

- [ ] **Step 1: Implement `login.py`**

```python
import argparse
import asyncio
import sys
from camoufox_session import make_camoufox, prepare_page, logged_in_youtube, log


async def run(headless):
    async with make_camoufox(headless) as ctx:
        page = await prepare_page(ctx)
        await page.goto("https://studio.youtube.com",
                        wait_until="domcontentloaded", timeout=60_000)
        log("Sign into the TARGET YouTube account in this window.")
        for _ in range(3600):  # up to ~1h
            if await logged_in_youtube(page):
                log("Logged in — session saved to .camoufox_profile/. You can close now.")
                await page.wait_for_timeout(2000)
                return 0
            await page.wait_for_timeout(1000)
        log("Timed out waiting for sign-in.")
        return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    return asyncio.run(run(a.headless))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manual — create venv, install, fetch browser**

Run:
```bash
python3.11 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python -m camoufox fetch
```
Expected: install completes; Camoufox browser downloaded.

- [ ] **Step 3: Manual — log into the target account**

Run: `venv/bin/python login.py`
Action: sign into the dedicated YouTube account in the window.
Expected: "Logged in — session saved".

- [ ] **Step 4: Manual — end-to-end publish (private, short clip)**

Prepare a **<15 min** test clip at `input/test.mp4`. Run:
```bash
venv/bin/python publish.py --video input/test.mp4 \
  --title "publish test" --visibility private \
  --channel-handle @<target> --keep-open --debug
```
Expected: log shows duration ok → selected → title set → Next×3 → visibility private → clicked Save → `RESULT: status=present|processing`. If a "Verify it's you" gate appears, clear it in the window; the run continues.

- [ ] **Step 5: Commit**

```bash
git add login.py
git commit -m "feat: one-time login flow for the target account"
```

---

### Task 10: Publish to GitHub

**Files:** none (operational)

- [ ] **Step 1: Secret audit (must be clean)**

Run: `bash scripts/audit_secrets.sh`
Expected: `secret audit clean` (exit 0). If it lists anything, STOP and fix `.gitignore` / untrack before continuing.

- [ ] **Step 2: Confirm tracked files contain no secrets**

Run: `git ls-files`
Expected: only source, tests, docs, README, requirements, hooks, scripts — NO `.camoufox_profile`, `.sqlite`, `cookies*.json`, `debug/`, `input/`, `output/`.

- [ ] **Step 3: Create the public repo and push**

Run:
```bash
gh repo create suenot/video_youtube_publish --public --source=. --remote=origin --push
```
Expected: repo created, initial push succeeds.

- [ ] **Step 4: Post-push audit on the remote**

Run: `gh api repos/suenot/video_youtube_publish/git/trees/HEAD?recursive=1 --jq '.tree[].path' | grep -E 'camoufox|\.sqlite|cookies.*json|^debug/' || echo "remote clean"`
Expected: `remote clean`.

---

## Self-Review

**Spec coverage:** independence/own profile → Tasks 6,9; login into separate account → Task 9; channel select → Task 7 + publish flow; length/verified pre-check → Task 3 + publish flow; verify result → Task 4 + publish flow; verify-gate handling → Task 5 + publish flow; security gitignore/hook/audit → Tasks 1,10; gh publish → Task 10; private default → Global Constraints + Task 8. All covered.

**Placeholder scan:** none — every code step has full code; manual browser steps have exact commands + expected observations.

**Type consistency:** `load_metadata`, `video_duration`, `check`, `parse_status`, `verify_gate_present`, `all_text`, `first_present`, `select_channel`, `channel_id_from_url` names/signatures match between their defining task and their use in `publish.py` (Task 8).

**Known limitation (documented, not a gap):** `verified` is hardcoded `False` in `run()` so long videos always require `--allow-long`; reading true channel-verified state from Studio is deferred (would be a `precheck.channel_verified(page)` browser probe). This is intentional YAGNI for v1 and noted in the spec's precheck interface.
