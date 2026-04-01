import os
import datetime
import smtplib
import asyncio
try:
    from imap_tools import MailBox, AND
    IMAP_AVAILABLE = True
except ImportError:
    IMAP_AVAILABLE = False
    print("imap-tools package not found.")

from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
RESUMES_RAW_DIR = Path("resumes_raw")
RESUMES_RAW_DIR.mkdir(exist_ok=True)

from app.core.config import settings

HR_SENDER_EMAIL = settings.HR_EMAIL

async def send_notification_email(subject: str, body: str):
    """Sends an email notification using SMTP."""
    email_user = settings.EMAIL_USER
    email_pass = settings.EMAIL_PASS
    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    
    if not email_user or not email_pass:
        print("SMTP credentials not set, skipping notification email.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = HR_SENDER_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(email_user, email_pass)
        server.send_message(msg)
        server.quit()
        print(f"Notification email sent: {subject}")
    except Exception as e:
        print(f"Failed to send notification email: {e}")

executor = ThreadPoolExecutor(max_workers=3)

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Throttling limit
INGEST_LIMIT = 5

def _sync_ingest():
    from app.services.resume_processor import process_resume_logic_sync
    from app.db.session import get_db_conn
    if not IMAP_AVAILABLE:
        logger.error("IMAP service unavailable - imap-tools not installed")
        return {"success": False, "message": "IMAP service unavailable"}
    
    email_user = settings.EMAIL_USER
    email_pass = settings.EMAIL_PASS
    email_host = settings.EMAIL_HOST
    
    if not email_user or not email_pass:
        logger.error("Email credentials not set in environment variables")
        return {"success": False, "message": "Email credentials not set"}

    processed_count = 0
    conn = get_db_conn()
    cursor = conn.cursor()
    
    try:
        logger.info(f"Connecting to IMAP server: {email_host}")
        # Added timeout to prevent hanging indefinitely
        with MailBox(email_host, timeout=30).login(email_user, email_pass) as mailbox:
            logger.info(f"Successfully logged in as {email_user}. Fetching unread emails from {HR_SENDER_EMAIL} (Limit: {INGEST_LIMIT})")
            
            # Only fetch unread emails from the specific HR sender, with a limit for throttling
            emails = mailbox.fetch(AND(seen=False, from_=HR_SENDER_EMAIL))
            
            for i, msg in enumerate(emails):
                if i >= INGEST_LIMIT:
                    logger.info(f"Reached ingestion limit of {INGEST_LIMIT} emails. Throttling...")
                    break
                
                # Check if email already processed using message_id
                cursor.execute("SELECT 1 FROM processed_emails WHERE message_id = ?", (msg.message_id,))
                if cursor.fetchone():
                    logger.info(f"Email with Message-ID {msg.message_id} already processed. Skipping.")
                    mailbox.flag(msg.uid, "\\Seen", True)
                    continue

                logger.info(f"Processing email: {msg.subject} from {msg.from_}")
                email_processed_successfully = False
                all_attachments = []
                
                for att in msg.attachments:
                    ext = Path(att.filename).suffix.lower()
                    if ext in [".pdf", ".docx", ".txt", ".jpg", ".png"]:
                        # Include message_id hash and a unique ID for absolute uniqueness
                        import uuid
                        msg_id_short = "".join(filter(str.isalnum, msg.message_id))[:10]
                        timestamp = int(datetime.datetime.now().timestamp())
                        unique_id = str(uuid.uuid4())[:8]
                        filename = f"email_{msg_id_short}_{timestamp}_{unique_id}_{Path(att.filename).name}"
                        filepath = RESUMES_RAW_DIR / filename
                        try:
                            with open(filepath, "wb") as f:
                                f.write(att.payload)
                            
                            logger.info(f"Saved attachment: {filename}")
                            
                            # Determine file type
                            file_type = "other"
                            if "resume" in att.filename.lower() or "cv" in att.filename.lower():
                                file_type = "resume"
                            elif "cover" in att.filename.lower() or "letter" in att.filename.lower():
                                file_type = "cover_letter"
                            elif ext in [".pdf", ".docx"] and not any(a["type"] == "resume" for a in all_attachments):
                                file_type = "resume" # Default first doc to resume if not specified
                            
                            all_attachments.append({
                                "path": filepath,
                                "content": att.payload,
                                "ext": ext,
                                "type": file_type,
                                "name": att.filename
                            })
                            
                            processed_count += 1
                            email_processed_successfully = True
                        except Exception as e:
                            logger.error(f"Failed to save attachment {att.filename}: {e}")
                            
                if email_processed_successfully:
                    # Process all attachments for this email together
                    # We'll pick the one marked as 'resume' as the primary
                    primary_resume = next((a for a in all_attachments if a["type"] == "resume"), all_attachments[0])
                    process_resume_logic_sync(primary_resume["path"], primary_resume["content"], primary_resume["ext"], all_attachments)
                    
                    # Record email as processed
                    cursor.execute("INSERT INTO processed_emails (message_id, processed_at) VALUES (?, ?)", 
                                 (msg.message_id, datetime.datetime.now().isoformat()))
                    conn.commit()
                
                mailbox.flag(msg.uid, "\\Seen", True)
                
        logger.info(f"Ingestion completed. Processed {processed_count} resumes.")
        return {"success": True, "processedCount": processed_count}
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"IMAP Ingestion Error: {str(e)}")
        
        # Check for specific IMAP error conditions
        if "authentication failed" in error_msg:
            return {"success": False, "message": "IMAP Authentication Failed. Please check your email credentials."}
        elif "timed out" in error_msg or "timeout" in error_msg:
            return {"success": False, "message": "IMAP Connection Timed Out. The server is taking too long to respond. Please try again later."}
        elif "quota exceeded" in error_msg or "mailbox full" in error_msg or "over quota" in error_msg:
            return {"success": False, "message": "IMAP Mailbox Full. Your email account has reached its storage limit. Please clear some space."}
        elif "connection" in error_msg or "network" in error_msg:
            return {"success": False, "message": "IMAP Connection Error. Could not connect to the email server. Please check your host settings and network connection."}
        
        return {"success": False, "message": f"An unexpected email ingestion error occurred: {str(e)}"}
    finally:
        conn.close()

async def perform_ingestion():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_ingest)
