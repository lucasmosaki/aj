# Instructions — Windows

## Requirements

- Windows 10 or later
- Python 3.8+ 
- Google Chrome, Firefox, or Microsoft Edge installed

---

## 1. Install Python

1. Go to python.org and download the latest Python 3 installer.
2. Run the installer. **Check the box "Add Python to PATH"** before clicking Install.
3. Open **Command Prompt** and verify:

```cmd
python --version
```

---

## 2. Create a virtual environment and install Selenium

Open **Command Prompt** (search for `cmd` in the Start menu):

```cmd
python -m venv %USERPROFILE%\selenium-env
%USERPROFILE%\selenium-env\Scripts\activate
pip install selenium
```

You must activate the environment every time you open a new Command Prompt before running the scheduler:

```cmd
%USERPROFILE%\selenium-env\Scripts\activate
```

> **PowerShell users:** If you use PowerShell instead of Command Prompt, run:
> ```powershell
> & "$env:USERPROFILE\selenium-env\Scripts\Activate.ps1"
> ```
> If you get a script execution error, first run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

## 3. Set up your schedule

Open `schedule.txt` in Notepad or any text editor and add your meetings. Remove the `#` from lines you want to activate.

| Format | When it opens |
|---|---|
| `HH:MM <url>` | Every day at that time |
| `Mon HH:MM <url>` | Every week on that day |
| `YYYY-MM-DD HH:MM <url>` | Once on that exact date |

Time is in 24-hour format (`09:00`, `14:30`).

---

## 4. Run the scheduler

Open **Command Prompt**, navigate to the project folder, and run:

```cmd
cd C:\path\to\aj
%USERPROFILE%\selenium-env\Scripts\activate
python main.py schedule.txt
```

To set your display name in the meeting:

```cmd
python main.py schedule.txt --name "Your Name"
```

Leave the Command Prompt window open. Press `Ctrl + C` to stop.

---

## 5. Run at startup (optional)

To have the scheduler start automatically when you log in:

1. Press `Win + R`, type `shell:startup`, and press Enter.
2. Create a new file called `start_scheduler.bat` in that folder with the following content (adjust the path):

```bat
@echo off
call %USERPROFILE%\selenium-env\Scripts\activate
python C:\path\to\aj\main.py C:\path\to\aj\schedule.txt
```

The scheduler will now launch automatically on login.

---

## Notes

- You can edit `schedule.txt` while the scheduler is running — it reloads automatically within 10 seconds.
- For Sympla links, the browser opens 10 minutes before the scheduled time and waits for the room to activate.
- If automation fails, the tool falls back to opening the URL in your default browser.
- Microsoft Edge is supported and will be detected automatically if it is your default browser.
