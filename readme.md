# Zoom Class Scheduler

Automatically opens your Zoom class links and clicks **Join** at the scheduled time — no manual action needed.

---

## Requirements

- Python 3.8+
- Google Chrome or Firefox installed

Activate the virtual environment first, then install the dependency:

```bash
source ~/selenium-env/bin/activate
pip install selenium
```

> (LINUX) You need to activate the environment every time before running the scheduler:
> ```bash
> source ~/selenium-env/bin/activate
> ```

---

## Setup

1. Open `schedule.txt` and add your classes (see format below).
2. Run the scheduler from the terminal.

---

## Running

```bash
python3 zoom_scheduler.py schedule.txt
```

To set your display name that appears in the meeting:

```bash
python3 zoom_scheduler.py schedule.txt --name "Your Name"
```

Leave the terminal open. The scheduler checks the time every 10 seconds and opens your meeting automatically when it's time.

Press `Ctrl + C` to stop.

---

## Schedule File Format

Open `schedule.txt` and add one class per line. Lines starting with `#` are ignored.

| Format | When it opens |
|---|---|
| `HH:MM <url>` | Every day at that time |
| `Mon HH:MM <url>` | Every week on that day |
| `YYYY-MM-DD HH:MM <url>` | Once on that specific date |

**Days of the week:** `Mon` `Tue` `Wed` `Thu` `Fri` `Sat` `Sun`

**Time format:** 24-hour (`09:00`, `14:30`)

### Example

```
# Daily standup
09:00 https://zoom.us/j/1234567890

# Weekly lectures
Mon 10:30 https://zoom.us/j/9876543210
Wed 10:30 https://zoom.us/j/9876543210
Fri 10:30 https://zoom.us/j/9876543210

# One-time session
2026-06-10 14:00 https://zoom.us/j/1122334455
```

### Meetings with a password

Paste the full URL including `?pwd=...` — Zoom handles it automatically:

```
Mon 10:30 https://zoom.us/j/1234567890?pwd=yourpassword
```

---

## What happens at meeting time

1. The scheduler opens your Zoom link in your default browser.
2. It clicks **"Join from Your Browser"** automatically.
3. If `--name` was provided, it fills in your display name.
4. It clicks the **Join** button.
5. The browser window stays open — you take over from there.

---

## Tips

- You can edit `schedule.txt` while the scheduler is running — it reloads automatically within 10 seconds.
- Run it in a background terminal (e.g. `tmux` or `screen`) so you can keep using your computer normally.
- If the automation fails (Zoom page changed, network issue), it will fall back to just opening the URL and print a warning.
