#!/usr/bin/env python3
"""
main.py — Joins Zoom meetings automatically at scheduled times.
Supports direct Zoom links and Sympla meeting-room links.

Usage:
    python main.py <schedule.txt>
    python main.py <schedule.txt> --name "Your Name"

Schedule file format (one entry per line, # = comment):
    HH:MM <url>                 daily at that time
    Mon HH:MM <url>             every Monday at that time
    YYYY-MM-DD HH:MM <url>      once on that specific date

Requires:
    pip install selenium
"""

import sys
import time
import platform
import subprocess
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

# ── Browser detection ──────────────────────────────────────────────────────────

def detect_default_browser() -> str:
    system = platform.system()
    try:
        if system == "Linux":
            result = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5,
            )
            browser_id = result.stdout.strip().lower()
        elif system == "Darwin":
            # osascript returns e.g. "/Applications/Google Chrome.app/"
            result = subprocess.run(
                ["osascript", "-e", "POSIX path of (path to default web browser)"],
                capture_output=True, text=True, timeout=5,
            )
            browser_id = result.stdout.strip().lower()
        elif system == "Windows":
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            ) as key:
                # ProgId is e.g. "ChromeHTML", "FirefoxURL", "MSEdgeHTM"
                browser_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
        else:
            browser_id = ""
    except Exception:
        browser_id = ""

    if any(x in browser_id for x in ("chrome", "chromium")):
        return "chrome"
    if "firefox" in browser_id:
        return "firefox"
    if any(x in browser_id for x in ("edge", "msedge", "msedgehtm")):
        return "edge"
    # Safari has poor Selenium support — fall back to Chrome
    return "chrome"


def create_driver(browser: str):
    from selenium import webdriver

    if browser == "firefox":
        opts = webdriver.FirefoxOptions()
        return webdriver.Firefox(options=opts)

    if browser == "edge":
        opts = webdriver.EdgeOptions()
        opts.add_argument("--disable-blink-features=AutomationControlled")
        return webdriver.Edge(options=opts)

    opts = webdriver.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-external-protocol-dialogs")  # suppress xdg-open dialogs
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("prefs", {
        "protocol_handler.excluded_schemes": {"zoommtg": True, "zoomus": True},
        "profile.default_content_setting_values.popups": 1,
    })

    system = platform.system()
    if system == "Linux":
        candidates = [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome",
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Windows":
        import os
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        candidates = []

    for path in candidates:
        if Path(path).exists():
            opts.binary_location = path
            break

    return webdriver.Chrome(options=opts)


# ── Zoom join (reuses an existing driver) ─────────────────────────────────────

_BROWSER_JOIN_SELECTORS = [
    # Zoom web client — explicit "join from browser" text
    ("xpath",             "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                          "'abcdefghijklmnopqrstuvwxyz'),'join from your browser')]"),
    ("xpath",             "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                          "'abcdefghijklmnopqrstuvwxyz'),'join from browser')]"),
    ("xpath",             "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                          "'abcdefghijklmnopqrstuvwxyz'),'join from your browser')]"),
    # Legacy Zoom web UI — anchor by id
    ("id",                "btn_browser_join"),
    ("link_text",         "Join from Your Browser"),
]

_NAME_SELECTORS = [
    ("css",  "input#inputname"),
    ("css",  "input[placeholder*='Your Name']"),
    ("css",  "input[placeholder*='name']"),
    ("name", "name"),
]

_JOIN_BTN_SELECTORS = [
    ("id",    "joinBtn"),
    ("css",   "button#joinBtn"),
    ("css",   "button.join-btn"),
    ("xpath", "//button[normalize-space(text())='Join']"),
    ("xpath", "//input[@value='Join']"),
]


def _find_clickable(driver, selectors, timeout=12):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    by_map = {
        "id":               By.ID,
        "css":              By.CSS_SELECTOR,
        "xpath":            By.XPATH,
        "link_text":        By.LINK_TEXT,
        "partial_link_text": By.PARTIAL_LINK_TEXT,
        "name":             By.NAME,
    }
    for kind, selector in selectors:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by_map[kind], selector))
            )
        except TimeoutException:
            continue
    return None


def _click_audio_skip_js(driver, timeout=45):
    """
    JS-based search: find any visible button/link whose text contains a
    'skip audio/camera' keyword and click it. Returns the matched text or None.
    The new Zoom web client renders everything via React so XPath/Selenium
    selectors often miss elements — JS DOM traversal is more reliable.
    """
    _SKIP_KEYWORDS = [
        "continue without audio and video",
        "continue without microphone and camera",
        "continue without microphone",
        "without microphone and camera",
        "join without audio",
        "without audio and video",
        "continue without video",
        "continue without audio",
        "continue without",
        "without microphone",
    ]
    deadline = time.time() + timeout
    while time.time() < deadline:
        for kw in _SKIP_KEYWORDS:
            found = driver.execute_script("""
                var kw = arguments[0];
                var tags = ['button','a','span','div','p'];
                for (var t = 0; t < tags.length; t++) {
                    var els = document.getElementsByTagName(tags[t]);
                    for (var i = 0; i < els.length; i++) {
                        var el = els[i];
                        if (!el.offsetParent) continue;
                        var text = (el.textContent || '').toLowerCase().trim();
                        if (text && text.length < 100 && text.includes(kw)) {
                            el.click();
                            return text;
                        }
                    }
                }
                return null;
            """, kw)
            if found:
                return found
        time.sleep(1)
    return None


def _handle_zoom_page(driver, display_name: str):
    """Given a driver already on a Zoom page, click through the join flow."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains

    # Dismiss Zoom cookie banner if present
    for sel in ("button#onetrust-accept-btn-handler", "button[aria-label='Accept Cookies']"):
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].is_displayed():
            try:
                driver.execute_script("arguments[0].click();", els[0])
                time.sleep(0.5)
            except Exception:
                pass
            break
    for btn in driver.find_elements(By.TAG_NAME, "button"):
        if btn.is_displayed() and btn.text.strip().upper() in ("ACCEPT COOKIES", "ACCEPT ALL COOKIES"):
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
            except Exception:
                pass
            break

    # If audio/camera skip prompt is already visible (e.g. cached session), dismiss it
    found = _click_audio_skip_js(driver, timeout=3)
    if found:
        print(f"  Clicked audio skip (pre-join): {found!r}")
        return

    print("  On Zoom page — looking for 'Join from browser'...")
    join_link = _find_clickable(driver, _BROWSER_JOIN_SELECTORS, timeout=5)
    if join_link:
        try:
            ActionChains(driver).move_to_element(join_link).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", join_link)
        print("  Clicked 'Join from browser'")
    else:
        print("  No join-from-browser link — proceeding to name/join step.")

    if display_name:
        name_el = _find_clickable(driver, _NAME_SELECTORS, timeout=10)
        if name_el:
            name_el.clear()
            name_el.send_keys(display_name)
            print(f"  Entered name: {display_name}")

    join_btn = _find_clickable(driver, _JOIN_BTN_SELECTORS, timeout=10)
    if join_btn:
        join_btn.click()
        print("  Clicked Join.")
    else:
        print("  Join button not found — may have auto-joined.")

    # After clicking Join, the web client connects via WebSocket then shows the
    # audio/camera prompt. The new Zoom client (joinFlowPhase3) can take 30+ sec
    # to connect before the dialog appears — wait up to 45 s.
    print("  Waiting for audio/camera prompt (up to 45s)...")
    found = _click_audio_skip_js(driver, timeout=45)
    if found:
        print(f"  Clicked audio skip: {found!r} — in the meeting.")
    else:
        # Debug dump: show all visible interactive elements
        visible = driver.execute_script("""
            var result = [];
            var els = document.querySelectorAll('button, a, [role="button"]');
            for (var i = 0; i < els.length; i++) {
                var el = els[i];
                var text = (el.textContent || '').trim();
                if (text && el.offsetParent) result.push(text.substring(0, 70));
            }
            return result.slice(0, 25);
        """)
        print("  Audio prompt not found. Visible buttons/links on page:")
        for v in (visible or []):
            print(f"    {v!r}")


# ── Zoom URL helpers ──────────────────────────────────────────────────────────

def _zoom_to_webclient(url: str):
    """Convert zoom.us/j/ID?pwd=... to zoom.us/wc/ID/join?pwd=... (web client)."""
    import re
    m = re.search(r'(https?://[^/]*zoom\.us)/j/(\d+)', url)
    if not m:
        return None
    base, meeting_id = m.group(1), m.group(2)
    pwd = re.search(r'[?&]pwd=([^&#]+)', url)
    wc = f"{base}/wc/{meeting_id}/join"
    if pwd:
        wc += f"?pwd={pwd.group(1)}"
    return wc


# ── Sympla flow ────────────────────────────────────────────────────────────────

# The button text must contain one of these to be considered the transmission button
_SYMPLA_BTN_KEYWORDS = (
    "TRANSMISS", "ASSISTIR AO VIVO", "ACESSAR SALA", "ABRIR SALA", "ENTRAR NA SALA",
)

# These mean the button exists but the stream hasn't started yet
_SYMPLA_INACTIVE_KEYWORDS = (
    "NÃO INICIADA", "NAO INICIADA", "NOT STARTED",
)

_SYMPLA_POLL_INTERVAL = 20   # seconds between checks
_SYMPLA_MAX_WAIT      = 7200  # give up after 2 hours


def _sympla_button_is_active(btn) -> bool:
    """Return True only if this is the Sympla transmission button AND it is now active."""
    text = btn.text.upper().strip()
    if not text:
        return False
    # Must be the transmission button specifically — not generic page buttons
    if not any(kw in text for kw in _SYMPLA_BTN_KEYWORDS):
        return False
    # Inactive state — stream not started yet
    if any(kw in text for kw in _SYMPLA_INACTIVE_KEYWORDS):
        return False
    # HTML disabled attribute
    if btn.get_attribute("disabled"):
        return False
    # Zero-size means hidden/invisible — don't click it
    size = btn.size
    if size.get("width", 0) == 0 or size.get("height", 0) == 0:
        return False
    return True


def _join_via_sympla(url: str, display_name: str, browser: str):
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import InvalidSessionIdException

    def fresh_driver():
        d = create_driver(browser)
        d.get(url)
        time.sleep(3)
        return d

    driver = fresh_driver()
    print("  Sympla page loaded — waiting for join URL from Vue...")

    elapsed = 0
    while elapsed < _SYMPLA_MAX_WAIT:
        try:
            # ── Read urlExternal directly from the Vue component ──
            # Sympla fetches the Zoom join URL via AJAX (/meetingroom/getJoinUrl)
            # and stores it in the Vue instance's urlExternal property.
            # Reading it directly is more reliable than clicking and intercepting popups.
            result = driver.execute_script("""
                var el = document.getElementById('streaming');
                if (!el || !el.__vue__) return {state: 'no-vue', url: null};
                var vm = el.__vue__;
                var ref = (vm.chosenSettings && vm.chosenSettings.ref) || 'loading';
                return {state: ref, url: vm.urlExternal || null};
            """)
            state = result.get("state") if result else "error"
            zoom_url = result.get("url") if result else None
            print(f"  Vue state: {state}  urlExternal: {str(zoom_url)[:80] if zoom_url else 'not set yet'}")

            if zoom_url:
                wc_url = _zoom_to_webclient(zoom_url)
                target = wc_url or zoom_url
                print(f"  Navigating to web client: {target[:80]}")
                driver.get(target)
                time.sleep(3)
                _handle_zoom_page(driver, display_name)
                return

        except InvalidSessionIdException:
            print("  Browser session lost — reopening...")
            try:
                driver.quit()
            except Exception:
                pass
            driver = fresh_driver()
            continue

        except Exception as e:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {e.__class__.__name__}: {str(e)[:120]}")

        elapsed += _SYMPLA_POLL_INTERVAL
        remaining = (_SYMPLA_MAX_WAIT - elapsed) // 60
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Not open yet — retrying in {_SYMPLA_POLL_INTERVAL}s (~{remaining} min left)")
        time.sleep(_SYMPLA_POLL_INTERVAL)
        try:
            driver.refresh()
            time.sleep(2)
        except Exception:
            pass

    print("  Timed out waiting for Sympla room to open.")


# ── Unified entry point ────────────────────────────────────────────────────────

def open_meeting(url: str, display_name: str, browser: str):
    from selenium.common.exceptions import WebDriverException

    print(f"  Using browser: {browser}")
    if "sympla.com.br/meeting-room" in url:
        try:
            _join_via_sympla(url, display_name, browser)
        except Exception as e:
            print(f"  Sympla automation failed: {e}\n  Falling back to webbrowser.open()...")
            webbrowser.open(url)
    else:
        try:
            driver = create_driver(browser)
        except WebDriverException as e:
            print(f"  Could not launch {browser} ({e})\n  Falling back to webbrowser.open()...")
            webbrowser.open(url)
            return
        try:
            driver.get(url)
            time.sleep(2)
            _handle_zoom_page(driver, display_name)
        except Exception as e:
            print(f"  Automation error: {e}\n  Falling back to webbrowser.open()...")
            try:
                driver.quit()
            except Exception:
                pass
            webbrowser.open(url)


# ── Schedule parsing ───────────────────────────────────────────────────────────

SYMPLA_PREOPEN_MIN = 5  # open the browser this many minutes before the event


def _is_sympla(url: str) -> bool:
    return "sympla.com.br/meeting-room" in url


def _adjust_time(t, url: str):
    """Return open time: subtract SYMPLA_PREOPEN_MIN for Sympla URLs."""
    if not _is_sympla(url):
        return t
    base = datetime(2000, 1, 1, t.hour, t.minute)
    adjusted = base - timedelta(minutes=SYMPLA_PREOPEN_MIN)
    return adjusted.time()


def _adjust_datetime(dt, url: str):
    if not _is_sympla(url):
        return dt
    return dt - timedelta(minutes=SYMPLA_PREOPEN_MIN)


def parse_schedule(path: Path) -> list:
    entries = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        try:
            if len(parts) == 2:
                t = datetime.strptime(parts[0], "%H:%M").time()
                url = parts[1]
                open_t = _adjust_time(t, url)
                e = {"type": "daily", "time": open_t, "url": url, "label": f"daily at {parts[0]}"}
                if _is_sympla(url):
                    e["meeting_time"] = t
                entries.append(e)
            elif len(parts) == 3:
                if parts[0].lower() in WEEKDAY_MAP:
                    t = datetime.strptime(parts[1], "%H:%M").time()
                    wd = WEEKDAY_MAP[parts[0].lower()]
                    url = parts[2]
                    open_t = _adjust_time(t, url)
                    e = {"type": "weekly", "weekday": wd, "time": open_t, "url": url,
                         "label": f"every {WEEKDAY_NAMES[wd]} at {parts[1]}"}
                    if _is_sympla(url):
                        e["meeting_time"] = t
                    entries.append(e)
                else:
                    dt = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M")
                    url = parts[2]
                    open_dt = _adjust_datetime(dt, url)
                    e = {"type": "once", "datetime": open_dt, "url": url,
                         "label": f"once on {parts[0]} {parts[1]}"}
                    if _is_sympla(url):
                        e["meeting_datetime"] = dt
                    entries.append(e)
            else:
                print(f"  [line {lineno}] skipped (unrecognized format): {line!r}")
        except ValueError as e:
            print(f"  [line {lineno}] skipped ({e}): {line!r}")
    return entries


def next_trigger(entry: dict, now: datetime):
    if entry["type"] == "daily":
        c = now.replace(hour=entry["time"].hour, minute=entry["time"].minute, second=0, microsecond=0)
        if "meeting_time" in entry:
            mt = entry["meeting_time"]
            meeting_dt = now.replace(hour=mt.hour, minute=mt.minute, second=0, microsecond=0)
            if c <= now <= meeting_dt:
                return now
            if meeting_dt < now:
                c += timedelta(days=1)
        elif c <= now:
            c += timedelta(days=1)
        return c
    if entry["type"] == "weekly":
        days = (entry["weekday"] - now.weekday()) % 7
        c = (now + timedelta(days=days)).replace(
            hour=entry["time"].hour, minute=entry["time"].minute, second=0, microsecond=0)
        if "meeting_time" in entry:
            mt = entry["meeting_time"]
            meeting_dt = (now + timedelta(days=days)).replace(
                hour=mt.hour, minute=mt.minute, second=0, microsecond=0)
            if c <= now <= meeting_dt:
                return now
            if meeting_dt < now:
                c += timedelta(weeks=1)
        elif c <= now:
            c += timedelta(weeks=1)
        return c
    if entry["type"] == "once":
        if "meeting_datetime" in entry:
            preopen = entry["datetime"]
            meeting = entry["meeting_datetime"]
            if preopen <= now <= meeting:
                return now
            return preopen if now < preopen else None
        return entry["datetime"] if entry["datetime"] > now else None


def should_fire(entry: dict, now: datetime) -> bool:
    if entry["type"] == "daily":
        if "meeting_time" in entry:
            mt = entry["meeting_time"]
            t = now.time().replace(second=0, microsecond=0)
            return entry["time"] <= t <= mt
        return now.hour == entry["time"].hour and now.minute == entry["time"].minute
    if entry["type"] == "weekly":
        if now.weekday() != entry["weekday"]:
            return False
        if "meeting_time" in entry:
            mt = entry["meeting_time"]
            t = now.time().replace(second=0, microsecond=0)
            return entry["time"] <= t <= mt
        return now.hour == entry["time"].hour and now.minute == entry["time"].minute
    if entry["type"] == "once":
        if "meeting_datetime" in entry:
            return entry["datetime"] <= now <= entry["meeting_datetime"]
        dt = entry["datetime"]
        return now.date() == dt.date() and now.hour == dt.hour and now.minute == dt.minute
    return False


def format_eta(trigger: datetime, now: datetime) -> str:
    delta = int((trigger - now).total_seconds())
    if delta <= 0:
        return "now"
    if delta < 60:
        return "< 1 min"
    hours, rem = divmod(delta, 3600)
    mins = rem // 60
    return f"in {hours}h {mins}m" if hours else f"in {mins}m"


def print_schedule(entries: list, now: datetime):
    print(f"\nLoaded {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}:\n")
    for e in entries:
        trigger = next_trigger(e, now)
        eta = format_eta(trigger, now) if trigger else "expired"
        if _is_sympla(e["url"]):
            if trigger is None:
                open_str = "expired"
            elif trigger <= now:
                open_str = "open now"
            else:
                open_str = trigger.strftime("browser opens at %H:%M")
            print(f"  {e['label']:<30}  {eta:<16}  [sympla — {open_str}]")
        else:
            print(f"  {e['label']:<30}  {eta:<16}  [zoom]  {e['url'][:60]}")
    print()


# ── Main loop ──────────────────────────────────────────────────────────────────

def run(path: Path, display_name: str):
    print(f"zoom-scheduler — watching {path.resolve()}")

    browser = detect_default_browser()
    print(f"Detected default browser: {browser}")

    try:
        from selenium import webdriver  # noqa: F401
    except ImportError:
        print("\n[ERROR] selenium is not installed.")
        print("Install it with:  pip install selenium\n")
        sys.exit(1)

    entries = parse_schedule(path)
    if not entries:
        print("No valid entries found. Check the schedule file format.")
        sys.exit(1)

    print_schedule(entries, datetime.now())
    print("Running... (Ctrl+C to stop)\n")

    last_fired: dict = {}
    last_mtime = path.stat().st_mtime

    while True:
        try:
            mtime = path.stat().st_mtime
            if mtime != last_mtime:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Schedule file changed — reloading...\n")
                entries = parse_schedule(path)
                last_mtime = mtime
                last_fired.clear()
                print_schedule(entries, datetime.now())
        except FileNotFoundError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Schedule file missing — waiting...")
            time.sleep(10)
            continue

        now = datetime.now()

        for i, entry in enumerate(entries):
            if _is_sympla(entry["url"]):
                if entry["type"] == "once":
                    fire_k = entry.get("meeting_datetime", entry["datetime"]).strftime("%Y-%m-%d %H:%M")
                else:
                    fire_k = now.strftime("%Y-%m-%d")
            else:
                fire_k = now.strftime("%Y-%m-%d %H:%M")
            if last_fired.get(i) == fire_k:
                continue
            if should_fire(entry, now):
                print(f"[{now.strftime('%H:%M:%S')}] Opening: {entry['url'][:70]}")
                open_meeting(entry["url"], display_name, browser)
                last_fired[i] = fire_k

        time.sleep(10)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args else 1)

    schedule_path = Path(args[0])
    if not schedule_path.exists():
        print(f"Error: file not found: {schedule_path}")
        sys.exit(1)

    display_name = ""
    if "--name" in args:
        idx = args.index("--name")
        if idx + 1 < len(args):
            display_name = args[idx + 1]

    try:
        run(schedule_path, display_name)
    except KeyboardInterrupt:
        print("\nStopped.")
