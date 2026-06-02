# Instructions — macOS

## Requirements

- macOS 10.15 or later
- Python 3.8+ (check with `python3 --version`)
- Google Chrome or Firefox installed (Safari is not supported)

---

## 1. Install Python (if not installed)

Open **Terminal** and run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python
```

Or download directly from python.org.

---

## 2. Create a virtual environment and install Selenium

```bash
python3 -m venv ~/selenium-env
source ~/selenium-env/bin/activate
pip install selenium
```

You must activate the environment every time you open a new Terminal before running the scheduler:

```bash
source ~/selenium-env/bin/activate
```

---

## 3. Set up your schedule

Open `schedule.txt` in any text editor and add your meetings. Remove the `#` from lines you want to activate.

| Format | When it opens |
|---|---|
| `HH:MM <url>` | Every day at that time |
| `Mon HH:MM <url>` | Every week on that day |
| `YYYY-MM-DD HH:MM <url>` | Once on that exact date |

Time is in 24-hour format (`09:00`, `14:30`).

---

## 4. Run the scheduler

```bash
cd /path/to/aj
source ~/selenium-env/bin/activate
python3 main.py schedule.txt
```

To set your display name in the meeting:

```bash
python3 main.py schedule.txt --name "Your Name"
```

Leave the Terminal window open. Press `Ctrl + C` to stop.

---

## 5. Run in the background (optional)

Use `tmux` so you can close the terminal and keep the scheduler running:

```bash
brew install tmux
tmux new -s scheduler
source ~/selenium-env/bin/activate
python3 main.py schedule.txt
```

Detach with `Ctrl + B`, then `D`. Reattach later with:

```bash
tmux attach -t scheduler
```

---

## Notes

- You can edit `schedule.txt` while the scheduler is running — it reloads automatically within 10 seconds.
- For Sympla links, the browser opens 10 minutes before the scheduled time and waits for the room to activate.
- If automation fails, the tool falls back to opening the URL in your default browser.
