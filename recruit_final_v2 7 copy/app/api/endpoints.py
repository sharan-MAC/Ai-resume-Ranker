import json
import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from app.db.session import get_db_conn, hash_password
from app.models.schemas import JobCreate
from app.services.email_service import perform_ingestion, perform_full_ingest, RESUMES_RAW_DIR, send_notification_email
from app.services.resume_processor import process_resume_logic

router = APIRouter()

# ── AUTH ──────────────────────────────────────────────────────────────────────
@router.post("/login")
async def login(payload: dict):
    u = payload.get("username","").strip()
    p = payload.get("password","")
    if not u or not p:
        raise HTTPException(400, "Username and password required")
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=? AND password_hash=?", (u, hash_password(p)))
    user = cursor.fetchone(); conn.close()
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return {"success": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}

@router.get("/users")
async def get_users():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT id,username,role,created_at FROM users ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]; conn.close(); return rows

@router.post("/users")
async def create_user(payload: dict):
    u = payload.get("username","").strip()
    p = payload.get("password","")
    role = payload.get("role","recruiter")
    if not u or not p:
        raise HTTPException(400, "Username and password required")
    conn = get_db_conn(); cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
            (u, hash_password(p), role, datetime.datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        conn.close(); raise HTTPException(400, str(e))
    conn.close(); return {"success": True}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    conn = get_db_conn()
    conn.execute("DELETE FROM users WHERE id=? AND username!='admin'", (user_id,))
    conn.commit(); conn.close(); return {"success": True}

# ── STATS ─────────────────────────────────────────────────────────────────────
@router.get("/stats")
async def get_stats():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("""
        SELECT
          (SELECT COUNT(*) FROM candidates)           AS totalCandidates,
          (SELECT COUNT(*) FROM jobs)                 AS activeJobs,
          (SELECT COUNT(*) FROM finalized_candidates) AS shortlisted,
          (SELECT COUNT(*) FROM processed_emails)     AS emailsProcessed
    """)
    row = dict(cursor.fetchone()); conn.close(); return row

# ── CANDIDATES ────────────────────────────────────────────────────────────────
@router.get("/candidates")
async def get_candidates():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidates ORDER BY created_at DESC")
    rows = cursor.fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["skills"]      = json.loads(d.get("skills") or "[]")
        d["parsed_json"] = json.loads(d.get("parsed_json") or "{}")
        out.append(d)
    return out

@router.delete("/candidates/{candidate_id}")
async def delete_candidate(candidate_id: int):
    conn = get_db_conn()
    for tbl in ("rankings","finalized_candidates","candidate_attachments"):
        conn.execute(f"DELETE FROM {tbl} WHERE candidate_id=?", (candidate_id,))
    conn.execute("DELETE FROM candidates WHERE id=?", (candidate_id,))
    conn.commit(); conn.close(); return {"success": True}

@router.get("/candidates/{candidate_id}/attachments")
async def get_attachments(candidate_id: int):
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidate_attachments WHERE candidate_id=?", (candidate_id,))
    rows = [dict(r) for r in cursor.fetchall()]; conn.close(); return rows

# ── JOBS ──────────────────────────────────────────────────────────────────────
@router.get("/jobs")
async def get_jobs():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    rows = cursor.fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["required_skills"] = json.loads(d.get("required_skills") or "[]")
        out.append(d)
    return out

@router.post("/jobs")
async def create_job(job: JobCreate, background_tasks: BackgroundTasks):
    conn = get_db_conn(); cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO jobs (title,description,required_skills,created_at) VALUES (?,?,?,?)",
        (job.title, job.description, json.dumps(job.required_skills), now))
    job_id = cursor.lastrowid
    conn.commit(); conn.close()
    # Fast skill-based ranking runs immediately
    background_tasks.add_task(_fast_rank_wrapper, job_id)
    # AI ranking runs after (slower but more accurate)
    background_tasks.add_task(_rank_all_candidates_for_job, job_id)
    background_tasks.add_task(send_notification_email,
        f"New Job: {job.title}", f"Title: {job.title}\n{job.description}")
    return {"success": True, "job_id": job_id}

def _fast_rank_wrapper(job_id: int):
    import asyncio, threading
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: loop.run_until_complete(_fast_skill_rank_job(job_id))
        finally: loop.close()
    threading.Thread(target=run, daemon=True, name=f"fastrank-{job_id}").start()

@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int):
    conn = get_db_conn()
    conn.execute("DELETE FROM rankings WHERE job_id=?",            (job_id,))
    conn.execute("DELETE FROM finalized_candidates WHERE job_id=?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id=?",                    (job_id,))
    conn.commit(); conn.close(); return {"success": True}

# ── RANKINGS ──────────────────────────────────────────────────────────────────
@router.get("/rankings/{job_id}")
async def get_rankings(job_id: int):
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, c.name, c.skills, c.email, c.experience_years, c.parsed_json
        FROM rankings r
        JOIN candidates c ON r.candidate_id=c.id
        WHERE r.job_id=?
        ORDER BY r.match_score DESC
    """, (job_id,))
    rows = cursor.fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["skills"]      = json.loads(d.get("skills") or "[]")
        d["parsed_json"] = json.loads(d.get("parsed_json") or "{}")
        out.append(d)
    return out

@router.post("/rankings/rank-job/{job_id}")
async def rank_job_now(job_id: int, background_tasks: BackgroundTasks):
    """Manually trigger ranking of ALL existing candidates for a specific job."""
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs WHERE id=?", (job_id,))
    if not cursor.fetchone():
        conn.close(); raise HTTPException(404, "Job not found")
    conn.close()
    # Count candidates for ETA
    conn2 = get_db_conn(); cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) AS n FROM candidates"); n_cands = cur2.fetchone()["n"]; conn2.close()
    # Run fast skill ranking immediately, then AI ranking
    background_tasks.add_task(_fast_rank_wrapper, job_id)
    background_tasks.add_task(_rank_all_candidates_for_job, job_id)
    return {"success": True, "message": f"Ranking {n_cands} candidates — skill scores instant, AI scores in ~{n_cands*3}s"}

@router.post("/rankings/rank-all")
async def rank_all_now(background_tasks: BackgroundTasks):
    """Re-rank ALL candidates against ALL jobs."""
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT id FROM jobs")
    job_ids = [r["id"] for r in cursor.fetchall()]; conn.close()
    for jid in job_ids:
        background_tasks.add_task(_rank_all_candidates_for_job, jid)
    return {"success": True, "message": f"Re-ranking all candidates for {len(job_ids)} job(s)"}

async def _rank_all_candidates_for_job(job_id: int):
    """Background task: rank every AI-enriched candidate against this job."""
    import asyncio, threading
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_do_rank_job(job_id))
        finally:
            loop.close()
    threading.Thread(target=run, daemon=True, name=f"rank-job-{job_id}").start()

async def _do_rank_job(job_id: int):
    from app.services.ai_service import rank_candidate_for_job, get_embedding, cosine_similarity
    import asyncio
    conn = get_db_conn(); cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        job = cursor.fetchone()
        if not job: return

        cursor.execute("SELECT value FROM settings WHERE key='shortlist_threshold'")
        row = cursor.fetchone()
        threshold = float(row["value"]) if row else 75.0

        # Rank ALL candidates (ai_enriched OR not — use quick parse data if not enriched)
        cursor.execute("SELECT id, name, email, skills, experience_years, education, parsed_json, resume_path FROM candidates")
        candidates = cursor.fetchall()
        print(f"[RankJob] Ranking {len(candidates)} candidates for job: {job['title']}")

        job_emb = await get_embedding(job["description"])
        now = datetime.datetime.now().isoformat()

        for i, cand in enumerate(candidates):
            try:
                parsed = json.loads(cand["parsed_json"] or "{}")
                skills_raw = json.loads(cand["skills"] or "[]")
                # Build candidate data dict from DB columns (works even without AI enrichment)
                data = {
                    "name": cand["name"] or parsed.get("name", "Unknown"),
                    "email": cand["email"] or "",
                    "experience_years": cand["experience_years"] or parsed.get("experience_years", 0),
                    "education": cand["education"] or parsed.get("education", ""),
                    "technical_skills": [{"name": s} for s in skills_raw] if skills_raw else parsed.get("technical_skills", []),
                    "skills": skills_raw,
                }

                # Try to read resume text for better scoring
                resume_text = ""
                if cand["resume_path"]:
                    rp = Path(cand["resume_path"])
                    if rp.exists():
                        try:
                            from app.services.resume_processor import _extract_text
                            resume_text = _extract_text(rp, rp.suffix.lower())
                        except Exception: pass

                cand_emb = await get_embedding(resume_text[:3000] if resume_text else json.dumps(data))
                sem  = cosine_similarity(cand_emb, job_emb) * 100 if cand_emb and job_emb else 0
                rank = await rank_candidate_for_job(data, job["description"], resume_text[:1000])
                score = round((rank.get("score", 0) * 0.7) + (sem * 0.3), 2)

                cursor.execute("""
                    INSERT INTO rankings (job_id,candidate_id,match_score,analysis_summary,created_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(job_id,candidate_id) DO UPDATE SET
                      match_score=excluded.match_score,
                      analysis_summary=excluded.analysis_summary,
                      created_at=excluded.created_at
                """, (job_id, cand["id"], score, rank.get("analysis", ""), now))

                if score >= threshold:
                    cursor.execute("""
                        INSERT OR IGNORE INTO finalized_candidates
                          (job_id,candidate_id,status,created_at) VALUES (?,?,'Shortlisted',?)
                    """, (job_id, cand["id"], now))

                conn.commit()
                print(f"[RankJob] [{i+1}/{len(candidates)}] {data['name']} → {score}%")

                # Pause between API calls to avoid rate limits (2s between each)
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[RankJob] Error for candidate {cand['id']}: {e}")
                await asyncio.sleep(5)  # longer pause on error (likely rate limit)

        # Broadcast update to frontend
        try:
            from app.core.notifications import manager
            await manager.broadcast({"type": "RANKINGS_UPDATED", "job_id": job_id})
        except Exception: pass
        print(f"[RankJob] ✅ Done ranking {len(candidates)} candidates for job {job_id}")
    finally:
        conn.close()


async def _fast_skill_rank_job(job_id: int):
    """Instant skill-keyword matching — no AI calls, runs in < 1 second."""
    conn = get_db_conn(); cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        job = cursor.fetchone()
        if not job: return

        required = json.loads(job["required_skills"] or "[]")
        job_text = (job["title"] + " " + job["description"]).lower()
        cursor.execute("SELECT id, name, skills, experience_years, parsed_json FROM candidates")
        candidates = cursor.fetchall()
        now = datetime.datetime.now().isoformat()

        cursor.execute("SELECT value FROM settings WHERE key='shortlist_threshold'")
        row = cursor.fetchone()
        threshold = float(row["value"]) if row else 75.0

        for cand in candidates:
            skills = json.loads(cand["skills"] or "[]")
            parsed = json.loads(cand["parsed_json"] or "{}")
            all_skills = skills + [s.get("name","") if isinstance(s,dict) else s
                                   for s in parsed.get("technical_skills",[])]

            # Skill overlap score
            if required:
                matched = sum(1 for s in all_skills if any(r.lower() in s.lower() or s.lower() in r.lower() for r in required))
                skill_score = min(100, (matched / len(required)) * 100)
            else:
                skill_score = 50  # no required skills = everyone qualifies at 50%

            # Experience bonus (up to 20 pts)
            exp = cand["experience_years"] or 0
            exp_bonus = min(20, exp * 4)
            score = round(min(100, skill_score * 0.8 + exp_bonus), 1)

            cursor.execute("""
                INSERT INTO rankings (job_id,candidate_id,match_score,analysis_summary,created_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(job_id,candidate_id) DO UPDATE SET
                  match_score=MAX(excluded.match_score, rankings.match_score),
                  created_at=excluded.created_at
            """, (job_id, cand["id"], score,
                  f"Skill match: {int(skill_score)}% | Exp: {exp}yr", now))

            if score >= threshold:
                cursor.execute("""
                    INSERT OR IGNORE INTO finalized_candidates
                      (job_id,candidate_id,status,created_at) VALUES (?,?,'Shortlisted',?)
                """, (job_id, cand["id"], now))

        conn.commit()
        print(f"[FastRank] Instantly ranked {len(candidates)} candidates for job {job_id}")
        try:
            from app.core.notifications import manager
            await manager.broadcast({"type": "RANKINGS_UPDATED", "job_id": job_id})
        except Exception: pass
    finally:
        conn.close()

# ── EMAIL INGESTION ───────────────────────────────────────────────────────────
@router.post("/ingest/email")
async def ingest_emails():
    result = await perform_ingestion()
    conn = get_db_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('last_sync_at',?)",
                 (datetime.datetime.now().isoformat(),))
    conn.commit(); conn.close()
    return result

@router.get("/ingest/status")
async def ingest_status():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS n FROM processed_emails")
    emails = cursor.fetchone()["n"]
    cursor.execute("SELECT COUNT(*) AS n FROM candidates")
    cands = cursor.fetchone()["n"]
    cursor.execute("SELECT value FROM settings WHERE key='last_sync_at'")
    row = cursor.fetchone(); conn.close()
    return {"processedEmails": emails, "totalCandidates": cands,
            "lastSyncAt": row["value"] if row else None}

@router.post("/ingest/reset")
async def reset_processed():
    """Clear processed log AND immediately re-fetch all emails."""
    conn = get_db_conn()
    conn.execute("DELETE FROM processed_emails")
    conn.commit(); conn.close()
    # Now re-ingest everything
    result = await perform_full_ingest()
    return {"success": True, "message": f"Reset complete. {result.get('message', '')}",
            "processedCount": result.get("processedCount", 0)}

@router.get("/test/email")
@router.post("/test/email")
async def test_email():
    from app.core.config import settings as cfg
    try:
        from imap_tools import MailBox
        with MailBox(cfg.EMAIL_HOST, timeout=15).login(cfg.EMAIL_USER, cfg.EMAIL_PASS) as mb:
            folders = list(mb.folder.list())
            return {"success": True, "message": f"Connected as {cfg.EMAIL_USER}. {len(folders)} folders."}
    except Exception as e:
        return {"success": False, "message": str(e)}

# ── FILE UPLOAD ───────────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_resume(background_tasks: BackgroundTasks, resume: UploadFile = File(...)):
    ext = Path(resume.filename).suffix.lower()
    if ext not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(400, "Only PDF, DOCX, or TXT allowed")
    filename = f"manual_{int(datetime.datetime.now().timestamp())}_{resume.filename.replace(' ','_')}"
    filepath = RESUMES_RAW_DIR / filename
    content  = await resume.read()
    filepath.write_bytes(content)
    background_tasks.add_task(process_resume_logic, filepath, content, ext, None)
    return {"success": True, "message": f"Uploaded: {resume.filename}"}

# ── SETTINGS ──────────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_settings():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings")
    rows = {r["key"]: r["value"] for r in cursor.fetchall()}
    conn.close(); return rows

@router.post("/settings")
async def update_settings(new_settings: dict):
    conn = get_db_conn()
    for k, v in new_settings.items():
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (k, str(v)))
    conn.commit(); conn.close(); return {"success": True}

# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
@router.get("/notifications")
async def get_notifications():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cursor.fetchall()]; conn.close(); return rows

@router.post("/notifications/read")
async def mark_read():
    conn = get_db_conn()
    conn.execute("UPDATE notifications SET is_read=1")
    conn.commit(); conn.close(); return {"success": True}

# ── SYSTEM HEALTH ─────────────────────────────────────────────────────────────
@router.get("/system/health")
async def system_health():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS c FROM candidates"); cands = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM jobs");       jobs  = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM rankings");   ranks = cursor.fetchone()["c"]
    conn.close()
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat(),
            "candidates": cands, "jobs": jobs, "rankings": ranks}

# ── ACTIVITIES ────────────────────────────────────────────────────────────────
@router.get("/activities")
async def get_activities():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("""
        SELECT 'candidate_added' AS type, 'New candidate: '||name AS description, created_at
        FROM candidates ORDER BY created_at DESC LIMIT 20
    """)
    rows = [dict(r) for r in cursor.fetchall()]; conn.close(); return rows

@router.get("/sync/history")
async def sync_history():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT message_id,processed_at FROM processed_emails ORDER BY processed_at DESC LIMIT 30")
    rows = [dict(r) for r in cursor.fetchall()]; conn.close(); return rows

# ── SHORTLISTED ───────────────────────────────────────────────────────────────
@router.get("/shortlisted")
async def get_shortlisted():
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("""
        SELECT fc.*, c.name, c.email, c.skills, c.experience_years, j.title AS job_title,
               r.match_score
        FROM finalized_candidates fc
        JOIN candidates c ON fc.candidate_id=c.id
        JOIN jobs j ON fc.job_id=j.id
        LEFT JOIN rankings r ON r.job_id=fc.job_id AND r.candidate_id=fc.candidate_id
        ORDER BY r.match_score DESC
    """)
    rows = cursor.fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["skills"] = json.loads(d.get("skills") or "[]")
        out.append(d)
    return out

# ── AI GLOBAL CHATBOT ─────────────────────────────────────────────────────────
@router.post("/chatbot")
async def global_chatbot(payload: dict):
    msg     = payload.get("message","").strip()
    history = payload.get("history",[])
    if not msg:
        raise HTTPException(400, "Message required")

    from app.services.ai_service import client, MODEL
    if not client:
        return {"response": "AI unavailable — check GEMINI_API_KEY in .env"}

    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT name,email,skills,experience_years,education,ai_enriched FROM candidates ORDER BY created_at DESC LIMIT 30")
    cands = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT title,description,required_skills FROM jobs")
    jobs_data = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) AS n FROM candidates");            total_c = cursor.fetchone()["n"]
    cursor.execute("SELECT COUNT(*) AS n FROM finalized_candidates");  shortlisted = cursor.fetchone()["n"]
    cursor.execute("SELECT COUNT(*) AS n FROM processed_emails");      emails_proc = cursor.fetchone()["n"]
    conn.close()

    for c in cands:
        try: c["skills"] = json.loads(c.get("skills") or "[]")
        except: pass

    system_prompt = f"""You are RecruitBot, an expert AI recruitment assistant for Recruit.AI.
Live data:
- Total Candidates: {total_c} | Shortlisted: {shortlisted} | Emails processed: {emails_proc}
- Candidates (latest 30): {json.dumps(cands)}
- Active Jobs: {json.dumps(jobs_data)}
Help recruiters with candidate analysis, skill gap analysis, job matching, pipeline status.
Be concise, specific, and data-driven. Use **bold** for names. Format lists with line breaks."""

    try:
        from app.services.ai_service import _generate, _retry
        # Build conversation with history
        conv_text = system_prompt + "\n\n"
        for h in history[-6:]:
            role = "You" if h.get("role") == "user" else "AI"
            conv_text += f"{role}: {h.get('text', h.get('content',''))}\n"
        conv_text += f"You: {msg}\nAI:"
        async def _do(): return await _generate(conv_text)
        response_text = await _retry(_do)
        return {"response": response_text}
    except Exception as e:
        return {"response": f"AI error: {str(e)[:300]}"}

# ── PER-CANDIDATE CHAT ────────────────────────────────────────────────────────
@router.post("/candidates/{candidate_id}/chat")
async def candidate_chat(candidate_id: int, payload: dict):
    msg = payload.get("message","").strip()
    if not msg: raise HTTPException(400, "Message required")
    conn = get_db_conn(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    cand = cursor.fetchone(); conn.close()
    if not cand: raise HTTPException(404, "Candidate not found")
    from app.services.ai_service import chat_with_ai
    ctx = f"Candidate: {json.dumps(dict(cand))}"
    resp = await chat_with_ai(msg, ctx)
    return {"text": resp}

# ── SEMANTIC SEARCH ───────────────────────────────────────────────────────────
@router.get("/search/semantic")
async def semantic_search(query: str):
    from app.services.ai_service import get_embedding
    from app.services.pinecone_service import query_candidates
    emb = await get_embedding(query)
    if not emb: return []
    matches = await query_candidates(emb)
    conn = get_db_conn(); cursor = conn.cursor()
    out = []
    for m in matches:
        cursor.execute("SELECT * FROM candidates WHERE id=?", (m.id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["skills"]      = json.loads(d.get("skills") or "[]")
            d["match_score"] = m.score
            out.append(d)
    conn.close(); return out
