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
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

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
    ("id",                "btn_browser_join"),
    ("link_text",         "Join from Your Browser"),
    ("partial_link_text", "join from your browser"),
    ("partial_link_text", "join from browser"),
    ("xpath",             "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                          "'abcdefghijklmnopqrstuvwxyz'),'join from your browser')]"),
]

_NAME_SELECTORS = [
    ("css",  "input#inputname"),
    ("css",  "input[placeholder*='Your Name']"),
    ("css",  "input[placeholder*='name']"),
    ("name", "name"),
]

_JOIN_BTN_SELECTORS = [
    ("id",    "joinBtn"),
    ("css",   "button.join-btn"),
    ("css",   "button#joinBtn"),
    ("xpath", "//button[contains(text(),'Join')]"),
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


def _handle_zoom_page(driver, display_name: str):
    """Given a driver already on a Zoom page, click through the join flow."""
    from selenium.common.exceptions import TimeoutException

    print("  On Zoom page — looking for 'Join from Your Browser'...")
    join_link = _find_clickable(driver, _BROWSER_JOIN_SELECTORS, timeout=15)
    if join_link:
        join_link.click()
        print("  Clicked 'Join from Your Browser'")
    else:
        print("  Could not find join-from-browser link.")

    if display_name:
        name_el = _find_clickable(driver, _NAME_SELECTORS, timeout=10)
        if name_el:
            name_el.clear()
            name_el.send_keys(display_name)
            print(f"  Entered name: {display_name}")

    join_btn = _find_clickable(driver, _JOIN_BTN_SELECTORS, timeout=10)
    if join_btn:
        join_btn.click()
        print("  Clicked Join — you should now be in the meeting.")
    else:
        print("  Join button not found; click it manually.")


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
    print("  Sympla page loaded — waiting for transmission button to activate...")

    elapsed = 0
    while elapsed < _SYMPLA_MAX_WAIT:
        try:
            # ── 1. Direct Zoom link already on the page ──
            zoom_anchors = driver.find_elements(By.XPATH, "//a[contains(@href,'zoom.us')]")
            if zoom_anchors:
                zoom_url = zoom_anchors[0].get_attribute("href")
                print(f"  Found Zoom link: {zoom_url}")
                driver.get(zoom_url)
                time.sleep(2)
                _handle_zoom_page(driver, display_name)
                return

            # ── 2. Transmission button active ──
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                if _sympla_button_is_active(btn):
                    print(f"  Button active: '{btn.text.strip()}' — clicking...")
                    btn.click()
                    time.sleep(4)

                    if "zoom.us" in driver.current_url:
                        _handle_zoom_page(driver, display_name)
                        return

                    zoom_anchors = driver.find_elements(By.XPATH, "//a[contains(@href,'zoom.us')]")
                    if zoom_anchors:
                        zoom_url = zoom_anchors[0].get_attribute("href")
                        print(f"  Zoom link found after redirect: {zoom_url}")
                        driver.get(zoom_url)
                        time.sleep(2)
                        _handle_zoom_page(driver, display_name)
                        return

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

SYMPLA_PREOPEN_MIN = 10  # open the browser this many minutes before the event


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
                entries.append({
                    "type": "daily", "time": open_t, "url": url,
                    "label": f"daily at {parts[0]}",
                })
            elif len(parts) == 3:
                if parts[0].lower() in WEEKDAY_MAP:
                    t = datetime.strptime(parts[1], "%H:%M").time()
                    wd = WEEKDAY_MAP[parts[0].lower()]
                    url = parts[2]
                    open_t = _adjust_time(t, url)
                    entries.append({
                        "type": "weekly", "weekday": wd, "time": open_t, "url": url,
                        "label": f"every {WEEKDAY_NAMES[wd]} at {parts[1]}",
                    })
                else:
                    dt = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M")
                    url = parts[2]
                    open_dt = _adjust_datetime(dt, url)
                    entries.append({
                        "type": "once", "datetime": open_dt, "url": url,
                        "label": f"once on {parts[0]} {parts[1]}",
                    })
            else:
                print(f"  [line {lineno}] skipped (unrecognized format): {line!r}")
        except ValueError as e:
            print(f"  [line {lineno}] skipped ({e}): {line!r}")
    return entries


def next_trigger(entry: dict, now: datetime):
    if entry["type"] == "daily":
        c = now.replace(hour=entry["time"].hour, minute=entry["time"].minute, second=0, microsecond=0)
        if c <= now:
            c += timedelta(days=1)
        return c
    if entry["type"] == "weekly":
        days = (entry["weekday"] - now.weekday()) % 7
        c = (now + timedelta(days=days)).replace(
            hour=entry["time"].hour, minute=entry["time"].minute, second=0, microsecond=0)
        if c <= now:
            c += timedelta(weeks=1)
        return c
    if entry["type"] == "once":
        return entry["datetime"] if entry["datetime"] > now else None


def should_fire(entry: dict, now: datetime) -> bool:
    if entry["type"] == "daily":
        return now.hour == entry["time"].hour and now.minute == entry["time"].minute
    if entry["type"] == "weekly":
        return (now.weekday() == entry["weekday"]
                and now.hour == entry["time"].hour
                and now.minute == entry["time"].minute)
    if entry["type"] == "once":
        dt = entry["datetime"]
        return now.date() == dt.date() and now.hour == dt.hour and now.minute == dt.minute
    return False


def format_eta(trigger: datetime, now: datetime) -> str:
    delta = int((trigger - now).total_seconds())
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
            open_str = trigger.strftime("browser opens at %H:%M") if trigger else "expired"
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
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        for i, entry in enumerate(entries):
            if last_fired.get(i) == minute_key:
                continue
            if should_fire(entry, now):
                print(f"[{now.strftime('%H:%M:%S')}] Opening: {entry['url'][:70]}")
                open_meeting(entry["url"], display_name, browser)
                last_fired[i] = minute_key

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
