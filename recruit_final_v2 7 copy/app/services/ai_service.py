"""
ai_service.py — Gemini AI with automatic model detection and rate-limit retry
Supports both google-generativeai (old SDK) and google-genai (new SDK)
"""
import os
import json
import asyncio
import numpy as np
from app.core.config import settings

# ── Try old SDK first (more stable, wider model support) ──
_genai_old = None
_OLD_OK = False
try:
    import google.generativeai as _genai_old
    if settings.GEMINI_API_KEY:
        _genai_old.configure(api_key=settings.GEMINI_API_KEY)
    _OLD_OK = True
    print("✅ google-generativeai SDK ready")
except Exception as e:
    print(f"⚠️  google-generativeai not available: {e}")

# ── Try new SDK as fallback ──
_genai_new_client = None
_NEW_OK = False
try:
    from google import genai as _genai_new
    if settings.GEMINI_API_KEY:
        _genai_new_client = _genai_new.Client(api_key=settings.GEMINI_API_KEY)
    _NEW_OK = True
    print("✅ google-genai (new SDK) ready")
except Exception as e:
    print(f"⚠️  google-genai not available: {e}")

# Export for endpoints
client = _genai_new_client
_USE_NEW_SDK = _NEW_OK
_OLD_SDK_OK = _OLD_OK

# Model to use — gemini-1.5-flash has highest free-tier quota
# Old SDK uses this name; new SDK uses "models/gemini-1.5-flash"
MODEL = "gemini-1.5-flash"
MODEL_NEW = "models/gemini-1.5-flash"
EMBED_MODEL = "models/text-embedding-004"

if not _OLD_OK and not _NEW_OK:
    print("❌ No Gemini SDK available — AI features disabled")


async def _retry(coro_fn, max_retries=3):
    """Exponential backoff retry on rate limit (429) errors."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            err = str(e)
            if any(x in err for x in ["429", "RESOURCE_EXHAUSTED", "quota", "rate"]):
                wait = 15 * (2 ** attempt)  # 15s, 30s, 60s
                print(f"[AI] Rate limited — retry {attempt+1}/{max_retries} after {wait}s")
                await asyncio.sleep(wait)
            elif "404" in err or "NOT_FOUND" in err:
                print(f"[AI] Model not found error: {err[:200]}")
                raise  # Don't retry model-not-found errors
            else:
                raise
    raise Exception("Max retries exceeded")


def _clean_json(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    for fence in ["```json\n", "```json", "```\n", "```"]:
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


async def _generate(prompt: str) -> str:
    """Generate text using whichever SDK is available."""
    if _OLD_OK:
        async def _call():
            m = _genai_old.GenerativeModel(MODEL)
            r = await m.generate_content_async(prompt)
            return r.text.strip()
        return await _retry(_call)
    elif _NEW_OK and _genai_new_client:
        async def _call():
            r = await _genai_new_client.aio.models.generate_content(
                model=MODEL_NEW, contents=prompt)
            return r.text.strip()
        return await _retry(_call)
    raise Exception("No AI SDK available")


async def extract_candidate_data(resume_text: str) -> dict:
    if not _OLD_OK and not _NEW_OK:
        return {}
    prompt = f"""Extract info from this resume. Return ONLY valid JSON, no markdown fences, no extra text.
{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "+91...",
  "technical_skills": [{{"name": "Python"}}, {{"name": "SQL"}}],
  "soft_skills": [{{"name": "Communication"}}],
  "education": "B.Tech Computer Science",
  "experience_years": 2.0,
  "previous_companies": ["Company A", "Company B"],
  "certifications": ["AWS Certified"],
  "summary": "Brief professional summary"
}}
Resume text:
{resume_text[:4000]}"""
    try:
        text = await _generate(prompt)
        return _clean_json(text)
    except Exception as e:
        print(f"[AI] extract_candidate_data failed: {e}")
        return {}


async def rank_candidate_for_job(candidate_data: dict, job_description: str, resume_text: str = "") -> dict:
    if not _OLD_OK and not _NEW_OK:
        return {"score": 0, "analysis": "AI unavailable"}

    # Build skills list from whatever format we have
    skills = candidate_data.get("skills", [])
    if not skills:
        tech = candidate_data.get("technical_skills", [])
        skills = [s["name"] if isinstance(s, dict) else str(s) for s in tech]

    prompt = f"""Score this candidate for the job 0-100. Return ONLY valid JSON, no markdown.
{{"score": 75, "analysis": "2-3 sentence explanation of fit"}}

Job: {job_description[:600]}
Candidate name: {candidate_data.get("name","Unknown")}
Skills: {", ".join(str(s) for s in skills[:15])}
Experience: {candidate_data.get("experience_years", 0)} years
Education: {candidate_data.get("education", "Not specified")}
Resume: {resume_text[:800]}"""
    try:
        text = await _generate(prompt)
        result = _clean_json(text)
        # Ensure score is a number 0-100
        score = float(result.get("score", 0))
        result["score"] = max(0, min(100, score))
        return result
    except Exception as e:
        print(f"[AI] rank_candidate_for_job failed: {e}")
        return {"score": 0, "analysis": str(e)[:150]}


async def get_embedding(text: str):
    """Get text embedding for semantic similarity."""
    if not _OLD_OK and not _NEW_OK:
        return None
    try:
        if _OLD_OK:
            async def _call():
                r = _genai_old.embed_content(
                    model=EMBED_MODEL,
                    content=text[:6000],
                    task_type="retrieval_document"
                )
                return r["embedding"]
            return await _retry(_call)
        elif _NEW_OK and _genai_new_client:
            async def _call():
                r = await _genai_new_client.aio.models.embed_content(
                    model=EMBED_MODEL, contents=text[:6000])
                return r.embeddings[0].values
            return await _retry(_call)
    except Exception as e:
        print(f"[AI] get_embedding failed: {e}")
        return None


async def chat_with_ai(message: str, context: str = "") -> str:
    if not _OLD_OK and not _NEW_OK:
        return "AI unavailable — please check GEMINI_API_KEY in .env"
    prompt = f"""You are a helpful recruitment AI assistant.
Context about our candidates and jobs:
{context[:2000]}

User question: {message}
Provide a helpful, concise answer."""
    try:
        return await _generate(prompt)
    except Exception as e:
        return f"AI error: {str(e)[:200]}"


def cosine_similarity(v1, v2) -> float:
    if v1 is None or v2 is None:
        return 0.0
    a, b = np.array(v1, dtype=float), np.array(v2, dtype=float)
    n = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / n) if n > 0 else 0.0


# Also export MODEL for endpoints.py
__all__ = ["extract_candidate_data", "rank_candidate_for_job", "get_embedding",
           "chat_with_ai", "cosine_similarity", "_retry", "MODEL", "_OLD_OK",
           "_NEW_OK", "client", "_USE_NEW_SDK", "_OLD_SDK_OK", "_generate"]
