"""
fetch_resumes.py - Downloads resumes from HR emails in the AI mailbox
"""

import os
import datetime
import uuid
from pathlib import Path

AI_EMAIL     = "scrh2k23@gmail.com"
AI_PASS      = ""
HR_EMAIL     = "sharanrh297@gmail.com"
IMAP_HOST    = "imap.gmail.com"
SAVE_DIR     = Path("downloaded_resumes")
ALLOWED_EXTS = {".pdf", ".docx", ".txt"}

try,

    from imap_tools import MailBox, AND
except ImportError:
    print("ERROR: imap-tools not installed.")
    print("Run:  pip3 install imap-tools")
    raise SystemExit(1)

SAVE_DIR.mkdir(exist_ok=True)

def fetch_resumes():
    print(f"Connecting to {IMAP_HOST} as {AI_EMAIL} ...")

    try:
        with MailBox(IMAP_HOST, timeout=30).login(AI_EMAIL, AI_PASS) as mailbox:
            print(f"Connected. Searching for emails from: {HR_EMAIL}\n")

            emails = list(mailbox.fetch(AND(from_=HR_EMAIL)))
            print(f"Found {len(emails)} email(s) from HR.\n")

            if not emails:
                print("No emails found from HR address.")
                print(f"Make sure HR is sending from exactly: {HR_EMAIL}")
                return

            total_saved = 0

            for msg in emails:
                print(f"Email  : {msg.subject or '(no subject)'}")
                print(f"From   : {msg.from_}")
                print(f"Date   : {msg.date}")

                resume_atts = [
                    att for att in msg.attachments
                    if Path(att.filename).suffix.lower() in ALLOWED_EXTS
                ]

                if not resume_atts:
                    print("  No resume attachments in this email.\n")
                    continue

                for att in resume_atts:
                    uid_part  = str(uuid.uuid4())[:6]
                    ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_name = att.filename.replace(" ", "_")
                    filename  = f"{ts}_{uid_part}_{safe_name}"
                    filepath  = SAVE_DIR / filename

                    with open(filepath, "wb") as f:
                        f.write(att.payload)

                    size_kb = len(att.payload) / 1024
                    print(f"  Saved: {filename}  ({size_kb:.1f} KB)")
                    total_saved += 1

                print()

            print("-" * 50)
            print(f"Done. {total_saved} resume(s) saved to: {SAVE_DIR.resolve()}")

    except Exception as e:
        err = str(e).lower()
        print(f"\nError: {e}\n")
        if "auth" in err or "login" in err:
            print("Authentication failed. Use a Gmail App Password, not your real password.")
            print("Google Account -> Security -> 2-Step Verification -> App Passwords")
        elif "timeout" in err:
            print("Connection timed out. Check your internet.")

if __name__ == "__main__":
    fetch_resumes()