#!/usr/bin/env python3
"""Quick test: immediately open the Sympla meeting-room link."""
import sys
sys.path.insert(0, "/home/osa/code/aj")
from main import open_meeting, detect_default_browser

URL = "https://www.sympla.com.br/meeting-room/FDlLpe3mCOjnuPv6MfZzEPlGx8FqU0m5Q4yEkBQ0CeIoQT7jAcZcd2o3tsyeC6uJFnEddH8ZmDpKbeF5FLUcDg"

browser = detect_default_browser()
print(f"Detected browser: {browser}")
open_meeting(URL, "Test User", browser)
print("Done.")
