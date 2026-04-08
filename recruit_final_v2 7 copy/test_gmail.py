#!/usr/bin/env python3
"""
Run this script to test Gmail connection and see ALL emails with attachments:
    python test_gmail.py

This will NOT modify any data - just shows what's in Gmail.
"""
import imaplib
import email
import email.header
from pathlib import Path

EMAIL = "scrh2k23@gmail.com"
PASS  = ""
HOST  = "imap.gmail.com"

def decode_header(value):
    if not value: return ""
    parts = email.header.decode_header(value)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(str(part))
    return " ".join(out)

print("="*60)
print("GMAIL DIAGNOSTIC TEST")
print("="*60)
print(f"Connecting to {HOST} as {EMAIL}...")

try:
    mail = imaplib.IMAP4_SSL(HOST, 993)
    mail.login(EMAIL, PASS)
    print("✅ Login successful!")
    
    mail.select("INBOX")
    status, data = mail.search(None, "ALL")
    all_ids = data[0].split()
    print(f"📬 Total emails in INBOX: {len(all_ids)}")
    
    if all_ids:
        print(f"   Newest ID: {all_ids[-1].decode()}")
        print(f"   Oldest ID: {all_ids[0].decode()}")
    
    print("\n📎 Scanning for emails with PDF/DOCX attachments...")
    found_resume_emails = 0
    
    # Check ALL emails
    for eid in all_ids:
        try:
            status, struct = mail.fetch(eid, "(BODYSTRUCTURE)")
            struct_str = str(struct)
            has_attach = any(x in struct_str.upper() for x in [
                "PDF", "DOCX", "MSWORD", "OFFICEDOCUMENT", "OCTET-STREAM"
            ])
            if has_attach:
                # Fetch full email to get subject
                status, msg_data = mail.fetch(eid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                subject = decode_header(msg.get("Subject", ""))
                sender  = decode_header(msg.get("From", ""))
                
                # Count actual attachments
                atts = []
                for part in msg.walk():
                    fn = part.get_filename()
                    if fn:
                        fn = decode_header(fn)
                        ext = Path(fn).suffix.lower()
                        if ext in {".pdf", ".docx", ".txt"}:
                            payload = part.get_payload(decode=True)
                            if payload and len(payload) > 500:
                                atts.append(f"{fn} ({len(payload)//1024}KB)")
                
                if atts:
                    found_resume_emails += 1
                    print(f"   ✓ ID={eid.decode()} | From: {sender[:40]} | Subject: {subject[:40]}")
                    for a in atts:
                        print(f"     📄 {a}")
        except Exception as e:
            pass
    
    print(f"\n✅ Found {found_resume_emails} emails with resume attachments")
    mail.logout()

except Exception as e:
    print(f"❌ ERROR: {e}")
    print("\nPossible fixes:")
    print("1. Enable 2FA on your Google account")
    print("2. Go to Google Account → Security → App Passwords")
    print("3. Create App Password for 'Mail' and update EMAIL_PASS in .env")
    print("4. Make sure IMAP is enabled: Gmail Settings → Forwarding & POP/IMAP → Enable IMAP")
