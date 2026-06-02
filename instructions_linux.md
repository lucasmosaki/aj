# Instructions — Linux

## Requirements

- Python 3.8+ (usually pre-installed)
- Google Chrome, Chromium, or Firefox installed

---

## 1. Check Python version

```bash
python3 --version
```

If Python is not installed:

```bash
sudo apt install python3 python3-pip python3-venv   # Debian/Ubuntu/Kali
```

---

## 2. Install a browser (if needed)

**Chromium:**
```bash
sudo apt install chromium-browser
```

**Google Chrome:**
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
```

**Firefox:**
```bash
sudo apt install firefox
```

---

## 3. Create a virtual environment and install Selenium

```bash
python3 -m venv ~/selenium-env
source ~/selenium-env/bin/activate
pip install selenium
```

You must activate the environment every time you open a new terminal before running the scheduler:

```bash
source ~/selenium-env/bin/activate
```

---

## 4. Set up your schedule

Open `schedule.txt` in any text editor and add your meetings. Remove the `#` from lines you want to activate.

| Format | When it opens |
|---|---|
| `HH:MM <url>` | Every day at that time |
| `Mon HH:MM <url>` | Every week on that day |
| `YYYY-MM-DD HH:MM <url>` | Once on that exact date |

Time is in 24-hour format (`09:00`, `14:30`).

---

## 5. Run the scheduler

```bash
cd /path/to/aj
source ~/selenium-env/bin/activate
python3 main.py schedule.txt
```

To set your display name in the meeting:

```bash
python3 main.py schedule.txt --name "Your Name"
```

Leave the terminal open. Press `Ctrl + C` to stop.

---

## 6. Run in the background (optional)

Use `tmux` or `screen` so the scheduler keeps running after you close the terminal:

```bash
sudo apt install tmux
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
- For Sympla links, the browser opens 5 minutes before the scheduled time and waits for the room to activate.
- If automation fails, the tool falls back to opening the URL in your default browser.
- On headless servers (no display), you may need to run Chrome with `--headless` or use a virtual display (`xvfb`).
