"""
resume_processor.py - Two-phase resume processing
Phase 1: Extract text + save to DB + instant skill-based ranking (<1 second)  
Phase 2: Gemini AI enrichment in background thread (fills skills, summary, re-ranks)
"""
import re
import json
import datetime
import asyncio
import threading
from pathlib import Path
from app.db.session import get_db_conn

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RESUMES_RAW_DIR = BASE_DIR / "resumes_raw"
RESUMES_RAW_DIR.mkdir(parents=True, exist_ok=True)
RESUMES_RAW = RESUMES_RAW_DIR  # alias

SKILL_LIST = [
    "Python","Java","JavaScript","TypeScript","React","Angular","Vue","Node.js",
    "SQL","MySQL","PostgreSQL","MongoDB","Redis","AWS","Azure","GCP","Docker",
    "Kubernetes","Git","Linux","HTML","CSS","Django","Flask","FastAPI","Spring",
    "Flutter","Swift","Kotlin","C++","C#","PHP","Ruby","Go","Rust","TensorFlow",
    "PyTorch","Machine Learning","Deep Learning","Data Science","Figma","Excel",
    "Tableau","Power BI","Spark","REST","GraphQL","DevOps","Agile","Scrum",
    "Next.js","Express","R","MATLAB","Selenium","Jenkins","Terraform","Jira",
    "Hadoop","Android","iOS","AI","NLP","Pandas","NumPy","Scikit-learn",
    "Keras","OpenCV","Computer Vision","Natural Language Processing",
    "Data Analysis","Business Analysis","Project Management","Cybersecurity",
    "Networking","Cloud Computing","Microservices","CI/CD","Testing","QA",
]


def _extract_text(filepath: Path, ext: str) -> str:
    """Extract plain text from PDF, DOCX, or TXT file."""
    text = ""
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(filepath))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        elif ext == ".docx":
            import mammoth
            with open(filepath, "rb") as f:
                text = mammoth.extract_raw_text(f).value
        elif ext == ".txt":
            text = filepath.read_text(errors="ignore")
    except Exception as e:
        print(f"[Extract] ⚠️  {filepath.name}: {e}")
    return text.strip()


def _quick_parse(text: str, filename: str) -> dict:
    """Fast regex-based parsing — runs in milliseconds."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Name: first short line without numbers/symbols
    name = Path(filename).stem.replace("_", " ").replace("-", " ").title()
    for line in lines[:15]:
        w = line.split()
        if 2 <= len(w) <= 5 and not re.search(r'[@:/\\0-9<>{}()\[\]|•=+]', line) and len(line) < 60:
            name = line
            break

    email_m = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    email   = email_m.group(0).lower() if email_m else ""

    phone_m = re.search(r"(\+?\d[\d\s\-(). ]{6,15}\d)", text)
    phone   = re.sub(r'\s+', ' ', phone_m.group(0).strip()) if phone_m else ""

    exp_m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", text, re.I)
    exp   = float(exp_m.group(1)) if exp_m else 0.0

    # Extract skills from full text
    found = []
    for skill in SKILL_LIST:
        if re.search(r'\b' + re.escape(skill) + r'\b', text, re.I):
            found.append(skill)

    return {
        "name":             name,
        "email":            email,
        "phone":            phone,
        "experience_years": exp,
        "education":        "",
        "technical_skills": [{"name": s} for s in found],
        "soft_skills":      [],
        "previous_companies": [],
        "certifications":   [],
        "summary":          "",
        "_ai_enriched":     False,
    }


def _instant_skill_rank(cid: int, skills: list, exp_years: float):
    """Rank new candidate against ALL jobs immediately using skill keywords."""
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jobs")
        jobs = cursor.fetchall()
        if not jobs:
            return

        cursor.execute("SELECT value FROM settings WHERE key='shortlist_threshold'")
        row = cursor.fetchone()
        threshold = float(row[0] if row else 75.0)
        now = datetime.datetime.now().isoformat()

        for job in jobs:
            req = json.loads(job["required_skills"] or "[]") if isinstance(job, dict) else json.loads(dict(job).get("required_skills", "[]"))
            job_id = job["id"] if isinstance(job, dict) else dict(job)["id"]

            if req:
                matched = sum(1 for s in skills
                              if any(r.lower() in s.lower() or s.lower() in r.lower() for r in req))
                skill_score = min(100, (matched / len(req)) * 100)
            else:
                skill_score = 40.0

            exp_bonus = min(20, exp_years * 4)
            score = round(min(100, skill_score * 0.8 + exp_bonus), 1)

            cursor.execute("""
                INSERT INTO rankings (job_id, candidate_id, match_score, analysis_summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(job_id, candidate_id) DO UPDATE SET
                  match_score = MAX(excluded.match_score, rankings.match_score),
                  analysis_summary = excluded.analysis_summary,
                  created_at = excluded.created_at
            """, (job_id, cid, score, f"Keyword match: {int(skill_score)}% | Exp: {exp_years}yr", now))

            if score >= threshold:
                cursor.execute("""
                    INSERT OR IGNORE INTO finalized_candidates
                      (job_id, candidate_id, status, created_at) VALUES (?, ?, 'Shortlisted', ?)
                """, (job_id, cid, now))

        conn.commit()
        print(f"[Processor] ⚡ Instant ranked candidate {cid} against {len(jobs)} job(s)")
    except Exception as e:
        print(f"[Processor] Instant rank error: {e}")
    finally:
        conn.close()


def _save_to_db(filepath: Path, text: str, all_attachments: list):
    """Save candidate to DB. Returns candidate ID or None."""
    data  = _quick_parse(text, filepath.name)
    skills = [s["name"] for s in data["technical_skills"]]
    conn   = get_db_conn()
    cursor = conn.cursor()
    try:
        # De-duplicate by resume path
        cursor.execute("SELECT id FROM candidates WHERE resume_path = ?", (str(filepath),))
        row = cursor.fetchone()
        if row:
            print(f"[Processor] Already in DB: {filepath.name}")
            return row[0]

        # De-duplicate by email
        if data["email"]:
            cursor.execute("SELECT id FROM candidates WHERE email = ?", (data["email"],))
            row = cursor.fetchone()
            if row:
                print(f"[Processor] Email already exists: {data['email']} → using existing id={row[0]}")
                return row[0]

        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO candidates
              (name, email, phone, skills, experience_years, education,
               resume_path, parsed_json, ai_enriched, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            data["name"], data["email"], data["phone"],
            json.dumps(skills), data["experience_years"], "",
            str(filepath), json.dumps(data), now
        ))
        cid = cursor.lastrowid

        # Save attachment records
        for att in (all_attachments or [{"path": filepath, "type": "resume"}]):
            cursor.execute(
                "INSERT INTO candidate_attachments (candidate_id, file_path, file_type, created_at) VALUES (?, ?, ?, ?)",
                (cid, str(att["path"]), att.get("type", "resume"), now)
            )

        # Add notification
        cursor.execute(
            "INSERT INTO notifications (title, message, type, created_at) VALUES (?, ?, ?, ?)",
            (
                f"New Resume: {data['name']}",
                f"From: {data['email'] or 'unknown'} | Skills: {', '.join(skills[:6]) or 'extracting...'}",
                "new_resume", now
            )
        )
        conn.commit()
        print(f"[Processor] ✅ Saved: {data['name']} | email={data['email']} | {len(skills)} skills | id={cid}")

        # Immediate skill-based ranking
        _instant_skill_rank(cid, skills, data["experience_years"])
        return cid

    except Exception as e:
        print(f"[Processor] ❌ DB save error: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def _run_ai_in_background(cid: int, text: str):
    """Launch AI enrichment in a daemon thread."""
    def _thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_ai_enrich(cid, text))
        except Exception as e:
            print(f"[AIEnrich] Thread crashed for cid={cid}: {e}")
        finally:
            loop.close()
    t = threading.Thread(target=_thread, daemon=True, name=f"ai-enrich-{cid}")
    t.start()
    print(f"[AIEnrich] Background thread started for candidate {cid}")


async def _ai_enrich(cid: int, text: str):
    """Gemini AI extraction — runs in background, updates DB when done."""
    print(f"[AIEnrich] 🤖 Starting Gemini extraction for candidate {cid}...")
    from app.services.ai_service import (
        extract_candidate_data, rank_candidate_for_job,
        get_embedding, cosine_similarity
    )

    # Step 1: Extract structured data
    data = await extract_candidate_data(text)
    if not data:
        print(f"[AIEnrich] ⚠️  No data returned for {cid} — AI quota exceeded or invalid response")
        return

    tech   = [s["name"] if isinstance(s, dict) else str(s) for s in data.get("technical_skills", [])]
    soft   = [s["name"] if isinstance(s, dict) else str(s) for s in data.get("soft_skills", [])]
    skills = list(dict.fromkeys(tech + soft))
    data["_ai_enriched"] = True

    conn   = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE candidates SET
              name=?, email=?, phone=?, skills=?,
              experience_years=?, education=?, parsed_json=?, ai_enriched=1
            WHERE id=?
        """, (
            data.get("name", "Unknown"),
            data.get("email", ""),
            data.get("phone", ""),
            json.dumps(skills),
            float(data.get("experience_years", 0)),
            data.get("education", ""),
            json.dumps(data),
            cid
        ))
        conn.commit()
        print(f"[AIEnrich] ✅ AI data saved: {data.get('name')} | {len(skills)} skills")

        # Notify frontend to refresh
        try:
            from app.core.notifications import manager
            await manager.broadcast({"type": "CANDIDATE_UPDATED", "id": cid})
        except Exception:
            pass

        # Step 2: Read shortlist threshold
        cursor.execute("SELECT value FROM settings WHERE key='shortlist_threshold'")
        row = cursor.fetchone()
        threshold = float(row[0] if row else 75.0)

        # Step 3: Re-rank against all jobs with AI accuracy
        emb = await get_embedding(text[:4000])
        cursor.execute("SELECT * FROM jobs")
        jobs = cursor.fetchall()

        for job in jobs:
            try:
                await asyncio.sleep(3)  # Rate limit buffer between API calls
                job_dict = dict(job)
                job_emb  = await get_embedding(job_dict["description"])
                sem      = cosine_similarity(emb, job_emb) * 100 if emb and job_emb else 0
                rank     = await rank_candidate_for_job(data, job_dict["description"], text[:800])
                score    = round((rank.get("score", 0) * 0.7) + (sem * 0.3), 2)
                now      = datetime.datetime.now().isoformat()

                cursor.execute("""
                    INSERT INTO rankings (job_id, candidate_id, match_score, analysis_summary, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, candidate_id) DO UPDATE SET
                      match_score=excluded.match_score,
                      analysis_summary=excluded.analysis_summary,
                      created_at=excluded.created_at
                """, (job_dict["id"], cid, score, rank.get("analysis", ""), now))

                if score >= threshold:
                    cursor.execute("""
                        INSERT OR IGNORE INTO finalized_candidates
                          (job_id, candidate_id, status, created_at) VALUES (?, ?, 'Shortlisted', ?)
                    """, (job_dict["id"], cid, now))

                print(f"[AIEnrich] Ranked vs '{job_dict['title']}': {score:.1f}%")
            except Exception as e:
                print(f"[AIEnrich] Ranking error for job: {e}")

        conn.commit()

        # Notify frontend rankings updated
        try:
            from app.core.notifications import manager
            await manager.broadcast({"type": "RANKINGS_UPDATED"})
        except Exception:
            pass

    except Exception as e:
        print(f"[AIEnrich] ❌ DB error: {e}")
    finally:
        conn.close()


def process_resume_logic_sync(filepath: Path, content: bytes, ext: str, all_attachments=None):
    """Entry point from email ingestion (runs in thread)."""
    text = _extract_text(filepath, ext)
    if not text:
        print(f"[Processor] ⚠️  No text extracted from {filepath.name}")
        return
    print(f"[Processor] 📝 Extracted {len(text)} chars from {filepath.name}")
    cid = _save_to_db(filepath, text, all_attachments)
    if cid:
        _run_ai_in_background(cid, text)


async def process_resume_logic(filepath: Path, content: bytes, ext: str, all_attachments=None):
    """Entry point from manual upload (async)."""
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _extract_text, filepath, ext)
    if not text:
        print(f"[Processor] ⚠️  No text from {filepath.name}")
        return
    cid = await loop.run_in_executor(None, _save_to_db, filepath, text, all_attachments)
    if cid:
        _run_ai_in_background(cid, text)
