#!/usr/bin/env python3
"""
Run this to immediately ingest ALL emails with resumes from Gmail.
Shows exactly what's happening in the terminal.

Usage:
    python ingest_now.py           # Only process new emails
    python ingest_now.py --all     # Re-process ALL emails (including seen ones)

This also starts the web server after ingestion is complete.
"""
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Load environment ──────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── Setup ─────────────────────────────────────────────────────────
import sqlite3
import imaplib
import email
import email.header
import uuid
import datetime
import json
import re
from pathlib import Path

BASE_DIR      = Path(__file__).resolve().parent
DB_PATH       = BASE_DIR / "recruitment.db"
RESUMES_DIR   = BASE_DIR / "resumes_raw"
RESUMES_DIR.mkdir(exist_ok=True)

EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
ALLOWED    = {".pdf", ".docx", ".txt"}
FORCE_ALL  = "--all" in sys.argv


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def decode_hdr(value):
    if not value: return ""
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


SKILL_LIST = [
    "Python","Java","JavaScript","TypeScript","React","Angular","Vue","Node.js",
    "SQL","MySQL","PostgreSQL","MongoDB","Redis","AWS","Azure","GCP","Docker",
    "Kubernetes","Git","Linux","HTML","CSS","Django","Flask","FastAPI","Spring",
    "Flutter","Swift","Kotlin","C++","C#","PHP","Ruby","Go","Rust","TensorFlow",
    "PyTorch","Machine Learning","Deep Learning","Data Science","Figma","Excel",
    "Tableau","Power BI","Spark","REST","GraphQL","DevOps","Agile","Scrum",
    "Next.js","Express","R","MATLAB","Selenium","Jenkins","Terraform","Jira",
    "Hadoop","Android","iOS","AI","NLP","Pandas","NumPy","Scikit-learn",
]


def extract_text(fpath, ext):
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            pages = []
            for page in PdfReader(str(fpath)).pages:
                t = page.extract_text()
                if t: pages.append(t)
            return "\n".join(pages).strip()
        elif ext == ".docx":
            import mammoth
            with open(fpath, "rb") as f:
                return mammoth.extract_raw_text(f).value.strip()
        elif ext == ".txt":
            return fpath.read_text(errors="ignore").strip()
    except Exception as e:
        print(f"    ⚠️  Text extract error: {e}")
    return ""


def quick_parse(text, filename):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = Path(filename).stem.replace("_"," ").replace("-"," ").title()
    for line in lines[:15]:
        w = line.split()
        if 2 <= len(w) <= 5 and not re.search(r'[@:/\\0-9<>{}()\[\]|•=+]', line) and len(line) < 60:
            name = line; break

    email_m = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    em = email_m.group(0).lower() if email_m else ""

    phone_m = re.search(r"(\+?\d[\d\s\-(). ]{6,15}\d)", text)
    ph = phone_m.group(0).strip() if phone_m else ""

    exp_m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", text, re.I)
    exp = float(exp_m.group(1)) if exp_m else 0.0

    skills = [s for s in SKILL_LIST if re.search(r'\b' + re.escape(s) + r'\b', text, re.I)]
    return {"name": name, "email": em, "phone": ph, "experience_years": exp,
            "skills": list(dict.fromkeys(skills))}


def save_candidate(fpath, text, all_atts):
    data = quick_parse(text, fpath.name)
    conn = get_db(); cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM candidates WHERE resume_path=?", (str(fpath),))
        row = cursor.fetchone()
        if row:
            print(f"    ↩️  Already in DB (by path): {fpath.name}")
            return

        if data["email"]:
            cursor.execute("SELECT id FROM candidates WHERE email=?", (data["email"],))
            row = cursor.fetchone()
            if row:
                print(f"    ↩️  Already in DB (by email): {data['email']}")
                return

        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO candidates
              (name, email, phone, skills, experience_years, education,
               resume_path, parsed_json, ai_enriched, created_at)
            VALUES (?,?,?,?,?,?,?,?,0,?)
        """, (
            data["name"], data["email"], data["phone"],
            json.dumps(data["skills"]), data["experience_years"], "",
            str(fpath), json.dumps(data), now
        ))
        cid = cursor.lastrowid

        for att in (all_atts or [{"path": fpath, "type": "resume"}]):
            cursor.execute(
                "INSERT INTO candidate_attachments (candidate_id, file_path, file_type, created_at) VALUES (?,?,?,?)",
                (cid, str(att["path"]), att.get("type","resume"), now)
            )

        cursor.execute(
            "INSERT INTO notifications (title, message, type, created_at) VALUES (?,?,?,?)",
            (f"New Resume: {data['name']}",
             f"Skills: {', '.join(data['skills'][:5])}",
             "new_resume", now)
        )

        # Fast skill-based ranking against all jobs
        cursor.execute("SELECT * FROM jobs")
        jobs = cursor.fetchall()
        cursor.execute("SELECT value FROM settings WHERE key='shortlist_threshold'")
        thresh_row = cursor.fetchone()
        threshold = float(thresh_row[0]) if thresh_row else 75.0

        for job in jobs:
            req = json.loads(dict(job).get("required_skills", "[]") or "[]")
            if req:
                matched = sum(1 for s in data["skills"]
                              if any(r.lower() in s.lower() or s.lower() in r.lower() for r in req))
                score = round(min(100, (matched / len(req)) * 100 * 0.8 + min(20, data["experience_years"]*4)), 1)
            else:
                score = 40.0

            cursor.execute("""
                INSERT INTO rankings (job_id, candidate_id, match_score, analysis_summary, created_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(job_id, candidate_id) DO UPDATE SET
                  match_score=MAX(excluded.match_score, rankings.match_score),
                  analysis_summary=excluded.analysis_summary
            """, (dict(job)["id"], cid, score, f"Keyword match: {score}%", now))

            if score >= threshold:
                cursor.execute("""
                    INSERT OR IGNORE INTO finalized_candidates
                      (job_id, candidate_id, status, created_at) VALUES (?,?,'Shortlisted',?)
                """, (dict(job)["id"], cid, now))

        conn.commit()
        skill_str = ", ".join(data["skills"][:5]) or "none detected"
        print(f"    ✅ Saved: {data['name']} | {data['email'] or 'no email'} | Skills: {skill_str}")
    except Exception as e:
        print(f"    ❌ DB error: {e}")
        conn.rollback()
    finally:
        conn.close()


def run():
    print("=" * 60)
    print("  RECRUIT.AI — GMAIL INGEST")
    print("=" * 60)

    if not EMAIL_USER or not EMAIL_PASS:
        print("❌ EMAIL_USER / EMAIL_PASS not set in .env")
        sys.exit(1)

    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT message_id FROM processed_emails")
    seen = {r[0] for r in cursor.fetchall()}
    conn.close()

    if FORCE_ALL:
        print(f"⚡ --all flag: re-processing ALL emails (ignoring {len(seen)} already seen)")
    else:
        print(f"📋 Already processed: {len(seen)} emails")

    print(f"Connecting to Gmail as {EMAIL_USER}...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL_USER, EMAIL_PASS)
        print(f"✅ Connected!")
    except imaplib.IMAP4.error as e:
        print(f"❌ Gmail login failed: {e}")
        print("\nTo fix:")
        print("1. Go to myaccount.google.com → Security")
        print("2. Enable 2-Step Verification")
        print("3. Go to App Passwords → create for Mail")
        print("4. Update EMAIL_PASS in .env with the 16-char password")
        print("5. Enable IMAP: Gmail Settings → Forwarding & POP/IMAP")
        sys.exit(1)

    mail.select("INBOX")
    status, data = mail.search(None, "ALL")
    all_ids = data[0].split()
    print(f"📬 Total emails in inbox: {len(all_ids)}")

    to_process = all_ids if FORCE_ALL else [e for e in all_ids if e.decode() not in seen]
    print(f"📨 Emails to process: {len(to_process)}")
    print("-" * 60)

    added = 0; errors = 0

    for idx, eid in enumerate(to_process, 1):
        uid = eid.decode()
        print(f"\n[{idx}/{len(to_process)}] Email uid={uid}")

        conn2 = get_db()
        conn2.execute(
            "INSERT OR IGNORE INTO processed_emails (message_id, processed_at) VALUES (?, ?)",
            (uid, datetime.datetime.now().isoformat())
        )
        conn2.commit(); conn2.close()

        try:
            # Check for attachments
            st, struct = mail.fetch(eid, "(BODYSTRUCTURE)")
            struct_str = str(struct).upper()
            has_att = any(x in struct_str for x in [
                "PDF","DOCX","MSWORD","OFFICEDOCUMENT","OCTET-STREAM","APPLICATION"
            ])
            if not has_att:
                print(f"  → No attachment")
                continue

            # Fetch full email
            st2, msg_data = mail.fetch(eid, "(RFC822)")
            if st2 != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                print(f"  → Fetch failed")
                continue

            msg     = email.message_from_bytes(msg_data[0][1])
            sender  = decode_hdr(msg.get("From", ""))
            subject = decode_hdr(msg.get("Subject", ""))
            print(f"  From: {sender[:60]}")
            print(f"  Subject: {subject[:60]}")

            saved_atts = []
            for part in msg.walk():
                fn = part.get_filename()
                if not fn: continue
                fn  = decode_hdr(fn)
                ext = Path(fn).suffix.lower()
                if ext not in ALLOWED: continue
                payload = part.get_payload(decode=True)
                if not payload or len(payload) < 200: continue

                ts   = int(datetime.datetime.now().timestamp())
                uid2 = str(uuid.uuid4())[:6]
                safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in fn)
                fname = f"{ts}_{uid2}_{safe}"
                fpath = RESUMES_DIR / fname
                fpath.write_bytes(payload)

                fl    = fn.lower()
                ftype = "cover_letter" if ("cover" in fl or "letter" in fl) else "resume"
                saved_atts.append({"path": fpath, "content": payload, "ext": ext, "type": ftype, "name": fn})
                print(f"  📄 {fn} ({len(payload)//1024} KB, {ftype})")

            if saved_atts:
                primary = next((a for a in saved_atts if a["type"] == "resume"), saved_atts[0])
                text = extract_text(primary["path"], primary["ext"])
                if text:
                    save_candidate(primary["path"], text, saved_atts)
                    added += 1
                else:
                    print(f"  ⚠️  Could not extract text from {primary['name']}")
            else:
                print(f"  → No valid PDF/DOCX found")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors += 1

    mail.logout()
    print("\n" + "=" * 60)
    print(f"✅ DONE! Added {added} candidates to database.")
    print(f"   Errors: {errors}")
    print("=" * 60)

    # Show DB summary
    conn3 = get_db(); cursor3 = conn3.cursor()
    cursor3.execute("SELECT COUNT(*) FROM candidates")
    total = cursor3.fetchone()[0]
    cursor3.execute("SELECT COUNT(*) FROM rankings")
    rankings = cursor3.fetchone()[0]
    conn3.close()
    print(f"📊 Database: {total} candidates | {rankings} rankings")
    print("\nNow start the server:  python main.py")


if __name__ == "__main__":
    run()
