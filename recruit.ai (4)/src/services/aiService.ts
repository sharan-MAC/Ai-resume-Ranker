import { settings } from "../core/config";
import { getSetting } from "../db/session";

let aiInstance: any = null;

async function getAI() {
  if (aiInstance) return aiInstance;
  const { GoogleGenAI } = await import("@google/genai");
  aiInstance = new GoogleGenAI({ apiKey: settings.GEMINI_API_KEY || "" });
  return aiInstance;
}

export const extractCandidateData = async (resumeText: string) => {
  if (!settings.GEMINI_API_KEY) return null;

  try {
    const ai = await getAI();
    const modelName = await getSetting('ai_model', 'gemini-3-flash-preview');
    const temperature = parseFloat(await getSetting('ai_temperature', '0.7'));
    
    const response = await ai.models.generateContent({
      model: modelName,
      contents: `Extract structured data from this resume. Return ONLY JSON.
      Format:
      {
        "name": "string",
        "email": "string",
        "phone": "string",
        "technical_skills": [{ "name": "string", "proficiency": "string" }],
        "soft_skills": [{ "name": "string", "proficiency": "string" }],
        "education": "string",
        "experience_years": float,
        "previous_companies": ["string"],
        "certifications": ["string"],
        "projects": ["string"]
      }
      Resume: ${resumeText}`,
      config: {
        responseMimeType: "application/json",
        temperature: temperature
      },
    });

    const text = response.text || "";
    return JSON.parse(text);
  } catch (error) {
    console.error("AI Extraction Error:", error);
    return null;
  }
};

export const rankCandidateForJob = async (candidateData: any, jobDescription: string, resumeText: string = "") => {
  if (!settings.GEMINI_API_KEY) return { score: 0, analysis: "AI service unavailable" };

  try {
    const ai = await getAI();
    const modelName = await getSetting('ai_model', 'gemini-3-flash-preview');
    const temperature = parseFloat(await getSetting('ai_temperature', '0.7'));

    const response = await ai.models.generateContent({
      model: modelName,
      contents: `Evaluate this candidate for the job based on the following criteria:
      1. Skill Match: How well do the candidate's technical and soft skills align with the job requirements?
      2. Experience Relevance: Is the candidate's past experience directly relevant to the role?
      3. Cultural Fit: Based on soft skills and communication style evident in the resume, how well would they fit a professional team environment?
      4. Long-Term Potential: Derived from project descriptions, certifications, and career progression, what is their potential for growth and leadership?
      5. Keyword Density: Does the resume naturally contain key industry terms related to the job?
      6. Semantic Alignment: How well does the overall profile match the job's context?

      Return ONLY a JSON object.
      Format: { 
        "score": number (0-100), 
        "analysis": "string", 
        "metrics": { 
          "skill_match": number, 
          "experience_relevance": number, 
          "cultural_fit": number,
          "long_term_potential": number,
          "keyword_density": number, 
          "semantic_alignment": number 
        } 
      }
      
      Candidate Data: ${JSON.stringify(candidateData)}
      Job Description: ${jobDescription}
      Full Resume Text (for context): ${resumeText.substring(0, 2000)}...`,
      config: {
        responseMimeType: "application/json",
        temperature: temperature
      },
    });

    const text = response.text || "";
    return JSON.parse(text);
  } catch (error) {
    console.error("AI Ranking Error:", error);
    return { score: 0, analysis: "Error during ranking" };
  }
};

export const chatWithResume = async (resumeText: string, userMessage: string, chatHistory: any[] = []) => {
  if (!settings.GEMINI_API_KEY) return { text: "AI service unavailable" };

  try {
    const ai = await getAI();
    const modelName = await getSetting('ai_model', 'gemini-3-flash-preview');
    const temperature = parseFloat(await getSetting('ai_temperature', '0.7'));

    const chat = ai.chats.create({
      model: modelName,
      config: {
        systemInstruction: `You are an expert recruiter assistant. You have access to a candidate's resume text. 
        Answer questions about the candidate based on the resume. 
        Be professional, concise, and helpful. 
        Candidate Resume: ${resumeText}`,
        temperature: temperature
      },
    });

    // Handle history if needed, but for now a simple message
    const response = await chat.sendMessage({ message: userMessage });
    return { text: response.text || "No response from AI" };
  } catch (error) {
    console.error("AI Chat Error:", error);
    return { text: "Error during chat with AI" };
  }
};

export const getEmbedding = async (text: string) => {
  if (!settings.GEMINI_API_KEY) return null;

  try {
    const ai = await getAI();
    const result = await ai.models.embedContent({
      model: "gemini-embedding-2-preview",
      contents: [text],
    });
    if (result.embeddings && result.embeddings.length > 0) {
      return result.embeddings[0].values;
    }
    return null;
  } catch (error) {
    console.error("AI Embedding Error:", error);
    return null;
  }
};

export const cosineSimilarity = (v1: number[], v2: number[]) => {
  if (!v1 || !v2) return 0;
  const dotProduct = v1.reduce((acc, val, i) => acc + val * v2[i], 0);
  const normV1 = Math.sqrt(v1.reduce((acc, val) => acc + val * val, 0));
  const normV2 = Math.sqrt(v2.reduce((acc, val) => acc + val * val, 0));
  if (normV1 === 0 || normV2 === 0) return 0;
  return dotProduct / (normV1 * normV2);
};
