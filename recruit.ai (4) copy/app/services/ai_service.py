import os
import json
from app.core.config import settings

try:
    import google.generativeai as genai
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("Google Generative AI package not found.")

model = None
if AI_AVAILABLE:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3-flash-preview')

async def extract_candidate_data(resume_text: str):
    if not model:
        return None
    prompt = f"""
    Extract structured data from this resume. Return ONLY JSON.
    Format:
    {{
      "name": "string",
      "email": "string",
      "phone": "string",
      "technical_skills": [{{ "name": "string", "proficiency": "string" }}],
      "soft_skills": [{{ "name": "string", "proficiency": "string" }}],
      "education": "string",
      "experience_years": float,
      "previous_companies": ["string"],
      "certifications": ["string"],
      "projects": ["string"]
    }}
    Resume: {resume_text}
    """
    try:
        response = await model.generate_content_async(prompt)
        if not response or not response.text:
            return None
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        return json.loads(text)
    except Exception as e:
        print(f"AI Extraction Error: {e}")
        return None

import numpy as np

def cosine_similarity(v1, v2):
    if v1 is None or v2 is None:
        return 0
    v1 = np.array(v1)
    v2 = np.array(v2)
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0
    return float(dot_product / (norm_v1 * norm_v2))

async def rank_candidate_for_job(candidate_data: dict, job_description: str, resume_text: str = ""):
    if not model:
        return {"score": 0, "analysis": "AI service unavailable"}
    
    # Enhanced prompt for more sophisticated metrics
    prompt = f"""
    Evaluate this candidate for the job based on the following criteria:
    1. Skill Match: How well do the candidate's technical and soft skills align with the job requirements?
    2. Experience Relevance: Is the candidate's past experience directly relevant to the role?
    3. Cultural Fit: Based on soft skills and communication style evident in the resume, how well would they fit a professional team environment?
    4. Long-Term Potential: Derived from project descriptions, certifications, and career progression, what is their potential for growth and leadership?
    5. Keyword Density: Does the resume naturally contain key industry terms related to the job?
    6. Semantic Alignment: How well does the overall profile match the job's context?

    Return ONLY a JSON object.
    Format: {{ 
      "score": number (0-100), 
      "analysis": "string", 
      "metrics": {{ 
        "skill_match": number, 
        "experience_relevance": number, 
        "cultural_fit": number,
        "long_term_potential": number,
        "keyword_density": number, 
        "semantic_alignment": number 
      }} 
    }}
    
    Candidate Data: {json.dumps(candidate_data)}
    Job Description: {job_description}
    Full Resume Text (for context): {resume_text[:2000]}...
    """
    try:
        response = await model.generate_content_async(prompt)
        if not response or not response.text:
            return {"score": 0, "analysis": "AI failed to generate a response"}
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        
        result = json.loads(text)
        
        # We can also manually calculate a semantic similarity score if we have embeddings
        # But for now, we'll trust the AI's contextual understanding which is quite good.
        
        return result
    except Exception as e:
        print(f"AI Ranking Error: {e}")
        return {"score": 0, "analysis": "Error during ranking"}

async def get_embedding(text: str):
    """Generates an embedding for the given text using Gemini."""
    if not AI_AVAILABLE:
        return None
    try:
        # Using the embedding model
        result = await genai.embed_content_async(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
            title="Resume Content"
        )
        return result['embedding']
    except Exception as e:
        print(f"AI Embedding Error: {e}")
        return None
