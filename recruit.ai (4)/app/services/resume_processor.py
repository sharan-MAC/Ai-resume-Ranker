import json
import datetime
import asyncio
from pathlib import Path
from app.db.session import get_db_conn

def process_resume_logic_sync(filepath: Path, content: bytes, ext: str, all_attachments: list = None):
    """Sync wrapper to run the async process_resume_logic."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_resume_logic(filepath, content, ext, all_attachments))
        loop.close()
    except Exception as e:
        print(f"Sync Resume Processing Error: {e}")

def _extract_text_sync(filepath: Path, ext: str):
    from pypdf import PdfReader
    import mammoth
    text = ""
    try:
        if ext == ".pdf":
            reader = PdfReader(filepath)
            for page in reader.pages:
                text += page.extract_text()
        elif ext == ".docx":
            with open(filepath, "rb") as docx_file:
                result = mammoth.extract_raw_text(docx_file)
                text = result.value
    except Exception as e:
        print(f"File Extraction Error: {e}")
    return text

async def process_resume_logic(filepath: Path, content: bytes, ext: str, all_attachments: list = None):
    from app.services.email_service import send_notification_email
    from app.services.ai_service import extract_candidate_data, rank_candidate_for_job, get_embedding
    from app.services.pinecone_service import upsert_candidate_vector
    from app.core.notifications import manager
    
    conn = get_db_conn()
    try:
        # Check if already processed
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM candidates WHERE resume_path = ?", (str(filepath),))
        if cursor.fetchone():
            return

        # Offload blocking file parsing to a thread
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _extract_text_sync, filepath, ext)

        if not text.strip():
            return

        data = await extract_candidate_data(text)
        if not data:
            return

        # Broadcast to UI
        notification_msg = {
            "type": "NEW_RESUME",
            "name": data.get("name", "Unknown"),
            "email": data.get("email", ""),
            "id": datetime.datetime.now().timestamp()
        }
        await manager.broadcast(notification_msg)

        # Store notification in DB
        cursor.execute("""
            INSERT INTO notifications (title, message, type, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            f"New Resume: {data.get('name', 'Unknown')}",
            f"Processed resume for {data.get('name', 'Unknown')} ({data.get('email', '')})",
            "new_resume",
            datetime.datetime.now().isoformat()
        ))

        tech_skills = data.get("technical_skills", [])
        soft_skills = data.get("soft_skills", [])
        combined_skills = []
        for s in tech_skills:
            combined_skills.append(s["name"] if isinstance(s, dict) else s)
        for s in soft_skills:
            combined_skills.append(s["name"] if isinstance(s, dict) else s)

        cursor.execute("""
            INSERT INTO candidates (name, email, phone, skills, experience_years, education, resume_path, parsed_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name", "Unknown"),
            data.get("email", ""),
            data.get("phone", ""),
            json.dumps(combined_skills),
            float(data.get("experience_years", 0)),
            data.get("education", ""),
            str(filepath),
            json.dumps(data),
            datetime.datetime.now().isoformat()
        ))
        candidate_id = cursor.lastrowid
        
        # Store all attachments
        if all_attachments:
            for att in all_attachments:
                cursor.execute("""
                    INSERT INTO candidate_attachments (candidate_id, file_path, file_type, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    candidate_id,
                    str(att["path"]),
                    att["type"],
                    datetime.datetime.now().isoformat()
                ))
        else:
            # If no all_attachments provided, at least store the primary resume
            cursor.execute("""
                INSERT INTO candidate_attachments (candidate_id, file_path, file_type, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                candidate_id,
                str(filepath),
                "resume",
                datetime.datetime.now().isoformat()
            ))

        conn.commit()

        # Vectorize and Store in Pinecone
        embedding = await get_embedding(text)
        if embedding:
            await upsert_candidate_vector(
                candidate_id=candidate_id,
                embedding=embedding,
                metadata={
                    "name": data.get("name", "Unknown"),
                    "email": data.get("email", ""),
                    "experience_years": float(data.get("experience_years", 0)),
                    "skills": combined_skills
                }
            )

        # Send notification for new candidate
        await send_notification_email(
            f"New Candidate Added: {data.get('name', 'Unknown')}",
            f"A new resume has been received and processed.\n\n"
            f"Name: {data.get('name', 'Unknown')}\n"
            f"Experience: {data.get('experience_years', 0)} years\n"
            f"Skills: {', '.join(combined_skills[:10])}..."
        )

        # Auto-Ranking
        from app.services.ai_service import cosine_similarity
        cursor.execute("SELECT * FROM jobs")
        jobs = cursor.fetchall()
        for job in jobs:
            # Semantic Similarity using Embeddings
            job_embedding = await get_embedding(job["description"])
            semantic_score = 0
            if embedding and job_embedding:
                semantic_score = cosine_similarity(embedding, job_embedding) * 100
            
            # AI-driven ranking with more metrics
            rank_result = await rank_candidate_for_job(data, job["description"], text)
            
            # Combine scores: 70% AI analysis (which now includes keyword density), 30% Semantic Similarity
            # This provides a balanced view of both explicit requirements and latent semantic match
            ai_score = rank_result.get("score", 0)
            final_score = (ai_score * 0.7) + (semantic_score * 0.3)
            
            # Update analysis to include semantic insights and detailed metrics
            analysis = rank_result.get("analysis", "")
            metrics = rank_result.get("metrics", {})
            
            if metrics:
                analysis += "\n\nAI Evaluation Metrics:\n"
                for metric_name, value in metrics.items():
                    # Format metric name for better readability
                    display_name = metric_name.replace("_", " ").title()
                    analysis += f"- {display_name}: {value}/100\n"
            
            if semantic_score > 0:
                analysis += f"\n\n[Semantic Match: {round(semantic_score, 1)}%]"
            
            cursor.execute("""
                INSERT INTO rankings (job_id, candidate_id, match_score, rank_position, analysis_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                job["id"],
                candidate_id,
                round(final_score, 2),
                None,
                analysis,
                datetime.datetime.now().isoformat()
            ))
            
            if final_score >= 80:
                cursor.execute("""
                    INSERT INTO finalized_candidates (job_id, candidate_id, status, created_at)
                    VALUES (?, ?, ?, ?)
                """, (job["id"], candidate_id, "Shortlisted", datetime.datetime.now().isoformat()))
                
                # Check notification settings
                cursor.execute("SELECT value FROM settings WHERE key = 'notify_shortlisted'")
                setting = cursor.fetchone()
                should_notify = setting["value"] == "true" if setting else True
                
                # Send notification for shortlisting if enabled
                if should_notify:
                    await send_notification_email(
                        f"Candidate Shortlisted: {data.get('name', 'Unknown')}",
                        f"A new candidate has been shortlisted for the position: {job['title']}\n\n"
                        f"Candidate: {data.get('name', 'Unknown')}\n"
                        f"Match Score: {round(final_score, 2)}%\n"
                        f"Analysis: {analysis}"
                    )
        conn.commit()
    except Exception as e:
        print(f"Error processing resume: {e}")
    finally:
        conn.close()
