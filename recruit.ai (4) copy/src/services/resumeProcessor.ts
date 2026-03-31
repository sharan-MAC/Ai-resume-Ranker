import fs from 'fs';
import path from 'path';
import pdf from 'pdf-parse';
import mammoth from 'mammoth';
import { queryOne, runQuery } from '../db/session';
import { extractCandidateData, rankCandidateForJob, getEmbedding, cosineSimilarity } from './aiService';
import { upsertCandidateVector } from './pineconeService';
import { manager } from '../core/notifications';
import { sendNotificationEmail } from './emailService';
import { queryAll } from '../db/session';

export const processResumeLogic = async (filepath: string, content: Buffer, ext: string, allAttachments: any[] = []) => {
  try {
    // Check if already processed
    const existing = await queryOne("SELECT id FROM candidates WHERE resume_path = ?", [filepath]);
    if (existing) {
      console.log(`[RESUME_PROCESSOR] Resume already processed: ${filepath}. Skipping.`);
      return;
    }

    console.log(`[RESUME_PROCESSOR] Starting processing for: ${filepath} (ext: ${ext})`);

    let text = "";
    if (ext === ".pdf") {
      try {
        const data = await (pdf as any)(content);
        text = data.text;
      } catch (pdfErr) {
        console.error(`[RESUME_PROCESSOR] PDF parsing failed for ${filepath}:`, pdfErr);
        throw new Error(`PDF parsing failed: ${pdfErr}`);
      }
    } else if (ext === ".docx") {
      try {
        const result = await mammoth.extractRawText({ buffer: content });
        text = result.value;
      } catch (docxErr) {
        console.error(`[RESUME_PROCESSOR] DOCX parsing failed for ${filepath}:`, docxErr);
        throw new Error(`DOCX parsing failed: ${docxErr}`);
      }
    }

    if (!text.trim()) {
      console.warn(`[RESUME_PROCESSOR] Extracted text is empty for ${filepath}. Skipping.`);
      return;
    }

    console.log(`[RESUME_PROCESSOR] Text extracted successfully (${text.length} chars). Extracting candidate data via AI...`);
    const data = await extractCandidateData(text);
    if (!data) {
      console.error(`[RESUME_PROCESSOR] AI failed to extract candidate data for ${filepath}.`);
      return;
    }

    console.log(`[RESUME_PROCESSOR] Candidate data extracted: ${data.name || 'Unknown'}. Saving to database...`);

    const systemSetting = await queryOne("SELECT value FROM settings WHERE key = 'system_notifications'");
    const shouldNotifySystem = systemSetting ? systemSetting.value === 'true' : true;

    if (shouldNotifySystem) {
      // Broadcast to UI
      const notificationMsg = {
        type: "NEW_RESUME",
        name: data.name || "Unknown",
        email: data.email || "",
        id: Date.now()
      };
      await manager.broadcast(notificationMsg);

      // Store notification in DB
      await runQuery(`
        INSERT INTO notifications (title, message, type, created_at)
        VALUES (?, ?, ?, ?)
      `, [
        `New Resume: ${data.name || 'Unknown'}`,
        `Processed resume for ${data.name || 'Unknown'} (${data.email || ''})`,
        "new_resume",
        new Date().toISOString()
      ]);
    }

    const techSkills = data.technical_skills || [];
    const softSkills = data.soft_skills || [];
    const combinedSkills = [
      ...techSkills.map((s: any) => typeof s === 'object' ? s.name : s),
      ...softSkills.map((s: any) => typeof s === 'object' ? s.name : s)
    ];

    const { lastID: candidateId } = await runQuery(`
      INSERT INTO candidates (name, email, phone, skills, experience_years, education, resume_path, resume_text, parsed_json, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `, [
      data.name || "Unknown",
      data.email || "",
      data.phone || "",
      JSON.stringify(combinedSkills),
      parseFloat(data.experience_years || 0),
      data.education || "",
      filepath,
      text,
      JSON.stringify(data),
      new Date().toISOString()
    ]);

    // Store attachments
    if (allAttachments && allAttachments.length > 0) {
      for (const att of allAttachments) {
        await runQuery(`
          INSERT INTO candidate_attachments (candidate_id, file_path, file_type, created_at)
          VALUES (?, ?, ?, ?)
        `, [candidateId, att.path, att.type, new Date().toISOString()]);
      }
    } else {
      await runQuery(`
        INSERT INTO candidate_attachments (candidate_id, file_path, file_type, created_at)
        VALUES (?, ?, ?, ?)
      `, [candidateId, filepath, "resume", new Date().toISOString()]);
    }

    // Vectorize and Store in Pinecone
    const embedding = await getEmbedding(text);
    if (embedding) {
      await upsertCandidateVector(candidateId, embedding, {
        name: data.name || "Unknown",
        email: data.email || "",
        experience_years: parseFloat(data.experience_years || 0),
        skills: combinedSkills
      });
    }

    // Send notification for new candidate
    const candidateSetting = await queryOne("SELECT value FROM settings WHERE key = 'notify_new_candidate'");
    const shouldNotifyCandidate = candidateSetting ? candidateSetting.value === 'true' : true;

    if (shouldNotifyCandidate) {
      await sendNotificationEmail(
        `New Candidate Added: ${data.name || 'Unknown'}`,
        `A new resume has been received and processed.\n\n` +
        `Name: ${data.name || 'Unknown'}\n` +
        `Experience: ${data.experience_years || 0} years\n` +
        `Skills: ${combinedSkills.slice(0, 10).join(', ')}...`
      );
    }

    // Auto-Ranking
    const jobs = await queryAll("SELECT * FROM jobs");
    for (const job of jobs) {
      const jobEmbedding = await getEmbedding(job.description);
      let semanticScore = 0;
      if (embedding && jobEmbedding) {
        semanticScore = cosineSimilarity(embedding, jobEmbedding) * 100;
      }

      const rankResult = await rankCandidateForJob(data, job.description, text);
      const aiScore = rankResult.score || 0;
      const finalScore = (aiScore * 0.7) + (semanticScore * 0.3);

      let analysis = rankResult.analysis || "";
      const metrics = rankResult.metrics || {};

      if (Object.keys(metrics).length > 0) {
        analysis += "\n\nAI Evaluation Metrics:\n";
        for (const [metricName, value] of Object.entries(metrics)) {
          const displayName = metricName.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
          analysis += `- ${displayName}: ${value}/100\n`;
        }
      }

      if (semanticScore > 0) {
        analysis += `\n\n[Semantic Match: ${Math.round(semanticScore * 10) / 10}%]`;
      }

      await runQuery(`
        INSERT INTO rankings (job_id, candidate_id, match_score, rank_position, analysis_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
      `, [
        job.id,
        candidateId,
        Math.round(finalScore * 100) / 100,
        null,
        analysis,
        new Date().toISOString()
      ]);

      if (finalScore >= 80) {
        await runQuery(`
          INSERT INTO finalized_candidates (job_id, candidate_id, status, created_at)
          VALUES (?, ?, ?, ?)
        `, [job.id, candidateId, "Shortlisted", new Date().toISOString()]);

        const setting = await queryOne("SELECT value FROM settings WHERE key = 'notify_shortlisted'");
        const shouldNotify = setting ? setting.value === 'true' : true;

        if (shouldNotify) {
          await sendNotificationEmail(
            `Candidate Shortlisted: ${data.name || 'Unknown'}`,
            `A new candidate has been shortlisted for the position: ${job.title}\n\n` +
            `Candidate: ${data.name || 'Unknown'}\n` +
            `Match Score: ${Math.round(finalScore * 100) / 100}%\n` +
            `Analysis: ${analysis}`
          );
        }
      }
    }
  } catch (error) {
    console.error("Error processing resume:", error);
  }
};
