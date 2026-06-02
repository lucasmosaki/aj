#!/usr/bin/env python3
"""
zoom_scheduler.py — Opens Zoom links in your default browser at scheduled times.

Usage:
    python zoom_scheduler.py <schedule.txt>

Schedule file format (one entry per line, # = comment):
    HH:MM <url>                 opens daily at that time
    Mon HH:MM <url>             opens every Monday at that time
    YYYY-MM-DD HH:MM <url>      opens once on that specific date
"""

import sys
import time
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
                entries.append({
                    "type": "daily",
                    "time": t,
                    "url": parts[1],
                    "label": f"daily at {parts[0]}",
                })
            elif len(parts) == 3:
                if parts[0].lower() in WEEKDAY_MAP:
                    t = datetime.strptime(parts[1], "%H:%M").time()
                    wd = WEEKDAY_MAP[parts[0].lower()]
                    entries.append({
                        "type": "weekly",
                        "weekday": wd,
                        "time": t,
                        "url": parts[2],
                        "label": f"every {WEEKDAY_NAMES[wd]} at {parts[1]}",
                    })
                else:
                    dt = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M")
                    entries.append({
                        "type": "once",
                        "datetime": dt,
                        "url": parts[2],
                        "label": f"once on {parts[0]} {parts[1]}",
                    })
            else:
                print(f"  [line {lineno}] skipped (unrecognized format): {line!r}")
        except ValueError as e:
            print(f"  [line {lineno}] skipped ({e}): {line!r}")
    return entries


def next_trigger(entry: dict, now: datetime):
    """Return the next datetime this entry fires, or None if already expired."""
    if entry["type"] == "daily":
        candidate = now.replace(
            hour=entry["time"].hour, minute=entry["time"].minute, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if entry["type"] == "weekly":
        days = (entry["weekday"] - now.weekday()) % 7
        candidate = (now + timedelta(days=days)).replace(
            hour=entry["time"].hour, minute=entry["time"].minute, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(weeks=1)
        return candidate

    if entry["type"] == "once":
        return entry["datetime"] if entry["datetime"] > now else None


def should_fire(entry: dict, now: datetime) -> bool:
    if entry["type"] == "daily":
        return now.hour == entry["time"].hour and now.minute == entry["time"].minute

    if entry["type"] == "weekly":
        return (
            now.weekday() == entry["weekday"]
            and now.hour == entry["time"].hour
            and now.minute == entry["time"].minute
        )

    if entry["type"] == "once":
        dt = entry["datetime"]
        return (
            now.date() == dt.date()
            and now.hour == dt.hour
            and now.minute == dt.minute
        )

    return False


def format_eta(trigger: datetime, now: datetime) -> str:
    delta = int((trigger - now).total_seconds())
    if delta < 60:
        return "< 1 min"
    hours, rem = divmod(delta, 3600)
    mins = rem // 60
    if hours:
        return f"in {hours}h {mins}m"
    return f"in {mins}m"


def print_schedule(entries: list, now: datetime):
    print(f"\nLoaded {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}:\n")
    active = 0
    for e in entries:
        trigger = next_trigger(e, now)
        if trigger:
            eta = format_eta(trigger, now)
            active += 1
        else:
            eta = "expired (past)"
        print(f"  {e['label']:<30}  {eta:<16}  {e['url']}")
    print()
    if active == 0:
        print("  All entries have already passed. Add future entries to the schedule file.")
    print()


def run(path: Path):
    print(f"zoom-scheduler — watching {path.resolve()}")

    entries = parse_schedule(path)
    if not entries:
        print("No valid entries found. Check the schedule file format and try again.")
        sys.exit(1)

    print_schedule(entries, datetime.now())
    print("Running... (Ctrl+C to stop)\n")

    last_fired: dict = {}   # entry index -> "YYYY-MM-DD HH:MM" of last open
    last_mtime = path.stat().st_mtime

    while True:
        # Reload file if it changed on disk
        try:
            mtime = path.stat().st_mtime
            if mtime != last_mtime:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Schedule file changed — reloading...\n")
                entries = parse_schedule(path)
                last_mtime = mtime
                last_fired.clear()
                print_schedule(entries, datetime.now())
        except FileNotFoundError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Schedule file missing — waiting for it to reappear...")
            time.sleep(10)
            continue

        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        for i, entry in enumerate(entries):
            # Prevent firing more than once per minute
            if last_fired.get(i) == minute_key:
                continue
            if should_fire(entry, now):
                print(f"[{now.strftime('%H:%M:%S')}] Opening: {entry['url']}")
                webbrowser.open(entry["url"])
                last_fired[i] = minute_key

        time.sleep(10)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        print("Example:")
        print("  python zoom_scheduler.py schedule.txt\n")
        sys.exit(1)

    schedule_path = Path(sys.argv[1])
    if not schedule_path.exists():
        print(f"Error: file not found: {schedule_path}")
        sys.exit(1)

    try:
        run(schedule_path)
    except KeyboardInterrupt:
        print("\nStopped.")
