"""
email_service.py — Gmail IMAP using raw imaplib
Fetches ALL emails (seen + unseen), processes ones with PDF/DOCX attachments.
Python 3.9 compatible.
"""
import imaplib
import email
import email.header
import smtplib
import asyncio
import logging
import uuid
import datetime
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

# Clear, visible terminal logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GMAIL] %(message)s",
    datefmt="%H:%M:%S",
    force=True
)
logger = logging.getLogger("email_service")

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RESUMES_RAW_DIR = BASE_DIR / "resumes_raw"
RESUMES_RAW_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".pdf", ".docx", ".txt"}
executor = ThreadPoolExecutor(max_workers=2)


def _decode_hdr(value: str) -> str:
    if not value:
        return ""
    try:
        parts = email.header.decode_header(value)
        out = []
        for part, enc in parts:
            if isinstance(part, bytes):
                out.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(str(part))
        return " ".join(out)
    except Exception:
        return str(value)


async def send_notification_email(subject: str, body: str):
    try:
        if not all([settings.EMAIL_USER, settings.EMAIL_PASS, settings.HR_EMAIL]):
            return
        msg = MIMEMultipart()
        msg["From"]    = settings.EMAIL_USER
        msg["To"]      = settings.HR_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
            s.ehlo(); s.starttls()
            s.login(settings.EMAIL_USER, settings.EMAIL_PASS)
            s.send_message(msg)
        logger.info(f"HR notified: {subject}")
    except Exception as e:
        logger.error(f"SMTP send failed: {e}")


def _do_ingest(force_all: bool = False) -> dict:
    """
    Main ingestion function.
    force_all=True: re-process ALL emails even if seen before (used by reset).
    force_all=False: only process emails not yet in processed_emails table.
    """
    from app.services.resume_processor import process_resume_logic_sync
    from app.db.session import get_db_conn

    if not settings.EMAIL_USER or not settings.EMAIL_PASS:
        return {"success": False, "message": "EMAIL_USER / EMAIL_PASS not set in .env"}

    conn   = get_db_conn()
    cursor = conn.cursor()
    added  = 0
    skipped = 0
    errors = 0

    try:
        logger.info("━" * 50)
        logger.info(f"Connecting to imap.gmail.com as {settings.EMAIL_USER}")
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(settings.EMAIL_USER, settings.EMAIL_PASS)
        logger.info("✅ Gmail connected")

        mail.select("INBOX")
        status, data = mail.search(None, "ALL")  # ALL = seen + unseen
        if status != "OK" or not data[0]:
            mail.logout(); conn.close()
            return {"success": True, "processedCount": 0, "message": "Inbox is empty"}

        all_ids = data[0].split()
        logger.info(f"📬 Total emails in INBOX: {len(all_ids)}")

        # Get already-processed IDs
        cursor.execute("SELECT message_id FROM processed_emails")
        seen_ids = {r[0] for r in cursor.fetchall()}
        logger.info(f"📋 Already processed: {len(seen_ids)} | New to check: {len(all_ids) - len(seen_ids)}")

        for idx, eid in enumerate(all_ids, 1):
            uid = eid.decode()

            if not force_all and uid in seen_ids:
                skipped += 1
                continue

            logger.info(f"[{idx}/{len(all_ids)}] Checking email uid={uid}...")

            # Mark processed FIRST — prevents infinite retry on crash
            cursor.execute(
                "INSERT OR IGNORE INTO processed_emails (message_id, processed_at) VALUES (?, ?)",
                (uid, datetime.datetime.now().isoformat())
            )
            conn.commit()

            try:
                # Quick structure check (no body download)
                st, struct_data = mail.fetch(eid, "(BODYSTRUCTURE)")
                struct_str = str(struct_data).upper()
                has_attach = any(x in struct_str for x in [
                    "PDF", "DOCX", "MSWORD", "OFFICEDOCUMENT",
                    "OCTET-STREAM", "VND.OPENXMLFORMATS", "APPLICATION"
                ])
                if not has_attach:
                    logger.info(f"  → No attachment, skip")
                    continue

                # Fetch full email
                st2, msg_data = mail.fetch(eid, "(RFC822)")
                if st2 != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    logger.warning(f"  → Failed to fetch body for uid={uid}")
                    continue

                raw  = msg_data[0][1]
                msg  = email.message_from_bytes(raw)
                sender  = _decode_hdr(msg.get("From", ""))
                subject = _decode_hdr(msg.get("Subject", ""))
                logger.info(f"  From: {sender[:50]}")
                logger.info(f"  Subject: {subject[:60]}")

                saved_atts = []
                for part in msg.walk():
                    filename = part.get_filename()
                    if not filename:
                        continue
                    filename = _decode_hdr(filename)
                    ext = Path(filename).suffix.lower()
                    if ext not in ALLOWED_EXT:
                        continue

                    payload = part.get_payload(decode=True)
                    if not payload or len(payload) < 200:
                        continue

                    ts       = int(datetime.datetime.now().timestamp())
                    uid_part = str(uuid.uuid4())[:6]
                    safe     = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
                    fname    = f"{ts}_{uid_part}_{safe}"
                    fpath    = RESUMES_RAW_DIR / fname

                    fpath.write_bytes(payload)
                    sz = len(payload) // 1024
                    fl = filename.lower()
                    ftype = "cover_letter" if ("cover" in fl or "letter" in fl) else "resume"

                    saved_atts.append({
                        "path":    fpath,
                        "content": payload,
                        "ext":     ext,
                        "type":    ftype,
                        "name":    filename,
                    })
                    logger.info(f"  📄 Saved: {fname} ({sz} KB, {ftype})")

                if saved_atts:
                    primary = next((a for a in saved_atts if a["type"] == "resume"), saved_atts[0])
                    process_resume_logic_sync(
                        primary["path"], primary["content"],
                        primary["ext"], saved_atts
                    )
                    added += 1
                    logger.info(f"  ✅ Resume #{added} added to database")
                else:
                    logger.info(f"  → No valid resume file found in attachments")

            except Exception as e:
                logger.error(f"  ❌ Error uid={uid}: {e}")
                errors += 1

        mail.logout()
        # Update last sync time
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync_at', ?)",
            (datetime.datetime.now().isoformat(),)
        )
        conn.commit()

        msg_out = (f"Added {added} new resume(s). "
                   f"Skipped {skipped} already seen. "
                   f"{errors} error(s).")
        logger.info(f"━━━ SYNC DONE: {msg_out} ━━━")
        return {"success": True, "processedCount": added, "message": msg_out}

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error: {e}")
        return {
            "success": False,
            "message": (
                f"Gmail error: {e}. "
                "Fix: Google Account → Security → App Passwords → create one for Mail. "
                "Also enable IMAP in Gmail Settings → Forwarding & POP/IMAP."
            )
        }
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        return {"success": False, "message": str(e)}
    finally:
        conn.close()


async def perform_ingestion() -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _do_ingest, False)


async def perform_full_ingest() -> dict:
    """Re-process ALL emails even if seen before."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _do_ingest, True)
