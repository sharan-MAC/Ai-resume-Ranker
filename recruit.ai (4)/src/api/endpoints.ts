import express, { Request, Response, NextFunction } from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import { queryAll, queryOne, runQuery } from '../db/session';
import { performIngestion, RESUMES_RAW_DIR, sendNotificationEmail, testEmailConnection } from '../services/emailService';
import { processResumeLogic } from '../services/resumeProcessor';
import { getEmbedding, chatWithResume } from '../services/aiService';
import { queryCandidates } from '../services/pineconeService';
import { hasPermission, Permission, Role } from '../core/rbac';

import bcrypt from 'bcryptjs';

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

// Health Check
router.get("/health", (req: Request, res: Response) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// RBAC Middleware
const authorize = (permission: Permission) => {
  return (req: Request, res: Response, next: NextFunction) => {
    const userRole = req.headers['x-user-role'] as Role;
    const userId = req.headers['x-user-id'] as string;
    const username = req.headers['x-user-username'] as string;
    
    if (!userRole) {
      return res.status(401).json({ error: 'Unauthorized: No role provided' });
    }

    // Attach user info to request for logging
    (req as any).user = { id: userId, username, role: userRole };

    if (hasPermission(userRole, permission)) {
      next();
    } else {
      res.status(403).json({ error: `Forbidden: Missing permission ${permission}` });
    }
  };
};

const logActivity = async (req: Request, action: string, details: string) => {
  const user = (req as any).user;
  if (user) {
    await runQuery(`
      INSERT INTO activities (user_id, username, action, details, created_at)
      VALUES (?, ?, ?, ?, ?)
    `, [user.id, user.username, action, details, new Date().toISOString()]);
  }
};

router.post("/test/email", authorize('manage_settings'), async (req: Request, res: Response) => {
  try {
    const result = await testEmailConnection();
    res.json(result);
  } catch (error) {
    console.error("Test Email Connection Error:", error);
    res.status(500).json({ success: false, error: "Internal server error during connection test" });
  }
});

router.post("/login", async (req: Request, res: Response) => {
  const { username, password } = req.body;
  try {
    const user = await queryOne("SELECT * FROM users WHERE username = ?", [username]);
    if (user && await bcrypt.compare(password, user.password)) {
      res.json({ 
        success: true, 
        user: { 
          id: user.id, 
          username: user.username, 
          role: user.role 
        } 
      });
    } else {
      res.status(401).json({ error: "Invalid username or password" });
    }
  } catch (error) {
    console.error("Login Error:", error);
    res.status(500).json({ error: "Login failed" });
  }
});

router.get("/search/semantic", authorize('view_candidates'), async (req: Request, res: Response) => {
  try {
    const query = req.query.query as string;
    if (!query) return res.json([]);
    const embedding = await getEmbedding(query);
    if (!embedding) return res.json([]);

    const matches = await queryCandidates(embedding);
    const results = [];

    for (const m of matches) {
      const candidate = await queryOne("SELECT * FROM candidates WHERE id = ?", [m.id]);
      if (candidate) {
        const d = { ...candidate };
        d.skills = JSON.parse(d.skills || "[]");
        d.match_score = m.score;
        results.push(d);
      }
    }

    res.json(results);
  } catch (error) {
    console.error("Semantic Search Error:", error);
    res.status(500).json({ error: "Search failed" });
  }
});

router.get("/stats", authorize('view_dashboard'), async (req: Request, res: Response) => {
  try {
    const row = await queryOne(`
      SELECT 
          (SELECT COUNT(*) FROM candidates) as totalCandidates,
          (SELECT COUNT(*) FROM jobs) as activeJobs,
          (SELECT COUNT(*) FROM finalized_candidates) as shortlisted
    `);
    res.json(row || { totalCandidates: 0, activeJobs: 0, shortlisted: 0 });
  } catch (error) {
    console.error("Stats Error:", error);
    res.status(500).json({ error: "Failed to fetch stats" });
  }
});

router.get("/candidates", authorize('view_candidates'), async (req: Request, res: Response) => {
  try {
    const candidates = await queryAll(`
      SELECT c.*, 
      (SELECT MAX(match_score) FROM rankings WHERE candidate_id = c.id) as top_match_score
      FROM candidates c 
      ORDER BY created_at DESC
    `);
    const result = candidates.map((c: any) => ({
      ...c,
      skills: JSON.parse(c.skills || "[]"),
      parsed_json: JSON.parse(c.parsed_json || "{}"),
      top_match_score: c.top_match_score || 0
    }));
    res.json(result);
  } catch (error) {
    console.error("Candidates Error:", error);
    res.status(500).json({ error: "Failed to fetch candidates" });
  }
});

router.get("/jobs", authorize('view_jobs'), async (req: Request, res: Response) => {
  try {
    const jobs = await queryAll("SELECT * FROM jobs ORDER BY created_at DESC");
    const result = jobs.map((j: any) => ({
      ...j,
      required_skills: JSON.parse(j.required_skills || "[]")
    }));
    res.json(result);
  } catch (error) {
    console.error("Jobs Error:", error);
    res.status(500).json({ error: "Failed to fetch jobs" });
  }
});

router.post("/jobs", authorize('manage_jobs'), async (req: Request, res: Response) => {
  const { title, description, required_skills } = req.body;
  await runQuery(`
    INSERT INTO jobs (title, description, required_skills, created_at)
    VALUES (?, ?, ?, ?)
  `, [title, description, JSON.stringify(required_skills), new Date().toISOString()]);

  await logActivity(req, 'CREATE_JOB', `Posted job: ${title}`);

  const setting = await queryOne("SELECT value FROM settings WHERE key = 'notify_new_job'");
  const shouldNotify = setting ? setting.value === 'true' : true;

  if (shouldNotify) {
    await sendNotificationEmail(
      `New Job Posted: ${title}`,
      `A new job opening has been created.\n\nTitle: ${title}\nDescription: ${description}\nSkills: ${required_skills.join(', ')}`
    );
  }

  res.json({ success: true });
});

router.get("/settings", authorize('manage_settings'), async (req: Request, res: Response) => {
  const settings = await queryAll("SELECT * FROM settings");
  const result = settings.reduce((acc: any, s: any) => {
    acc[s.key] = s.value;
    return acc;
  }, {} as any);
  res.json(result);
});

router.post("/settings", authorize('manage_settings'), async (req: Request, res: Response) => {
  const settings = req.body;
  for (const [key, value] of Object.entries(settings)) {
    await runQuery("UPDATE settings SET value = ? WHERE key = ?", [String(value), key]);
  }
  await logActivity(req, 'UPDATE_SETTINGS', 'Updated system settings');
  res.json({ success: true });
});

router.post("/ingest/email", authorize('manage_candidates'), async (req: Request, res: Response) => {
  console.log(`[API] Manual email ingestion triggered by user.`);
  try {
    const result = await performIngestion();
    if (result.success) {
      console.log(`[API] Email ingestion successful. Processed ${result.processedCount || 0} resumes.`);
    } else {
      console.error(`[API] Email ingestion failed: ${result.error || result.message}`);
    }
    res.json(result);
  } catch (error) {
    console.error(`[API] Unexpected error during email ingestion:`, error);
    res.status(500).json({ success: false, error: "Internal server error during ingestion" });
  }
});

router.post("/upload", authorize('manage_candidates'), upload.single('resume'), async (req: Request, res: Response) => {
  if (!req.file) return res.status(400).json({ error: "No file uploaded" });

  const ext = path.extname(req.file.originalname).toLowerCase();
  if (!['.pdf', '.docx'].includes(ext)) {
    return res.status(400).json({ error: "Unsupported file format" });
  }

  const filename = `manual_${path.parse(req.file.originalname).name}_${Date.now()}${ext}`;
  const filepath = path.join(RESUMES_RAW_DIR, filename);

  const content = fs.readFileSync(req.file.path);
  fs.writeFileSync(filepath, content);
  fs.unlinkSync(req.file.path);

  // Run in background
  processResumeLogic(filepath, content, ext);

  res.json({ success: true });
});

router.get("/notifications", authorize('view_dashboard'), async (req: Request, res: Response) => {
  const notifications = await queryAll("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50");
  res.json(notifications);
});

router.get("/users", authorize('manage_users'), async (req: Request, res: Response) => {
  const users = await queryAll("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC");
  res.json(users);
});

router.post("/users", authorize('manage_users'), async (req: Request, res: Response) => {
  const { username, password, role } = req.body;
  try {
    const hashedPassword = await bcrypt.hash(password, 10);
    await runQuery("INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)", [username, hashedPassword, role, new Date().toISOString()]);
    await logActivity(req, 'CREATE_USER', `Created user: ${username} with role: ${role}`);
    res.json({ success: true });
  } catch (error) {
    console.error("Create User Error:", error);
    res.status(500).json({ error: "Failed to create user" });
  }
});

router.delete("/users/:id", authorize('manage_users'), async (req: Request, res: Response) => {
  try {
    const userToDelete = await queryOne("SELECT username FROM users WHERE id = ?", [req.params.id]);
    await runQuery("DELETE FROM users WHERE id = ?", [req.params.id]);
    if (userToDelete) {
      await logActivity(req, 'DELETE_USER', `Deleted user: ${userToDelete.username}`);
    }
    res.json({ success: true });
  } catch (error) {
    console.error("Delete User Error:", error);
    res.status(500).json({ error: "Failed to delete user" });
  }
});

router.get("/activities", authorize('view_dashboard'), async (req: Request, res: Response) => {
  try {
    const activities = await queryAll("SELECT * FROM activities ORDER BY created_at DESC LIMIT 100");
    res.json(activities);
  } catch (error) {
    console.error("Activities Error:", error);
    res.status(500).json({ error: "Failed to fetch activities" });
  }
});

router.get("/system/health", authorize('manage_settings'), async (req: Request, res: Response) => {
  try {
    // Mock health checks for now, but in a real app these would be actual checks
    res.json({
      database: { status: 'ok', message: 'SQLITE_LOCAL_OK' },
      vector_search: { status: 'ok', message: 'PINECONE_CLOUD_UP' },
      gemini_api: { status: 'ok', message: 'GENAI_READY' },
      email_sync: { status: 'ok', message: 'IMAP_IDLE' }
    });
  } catch (error) {
    res.status(500).json({ error: "Health check failed" });
  }
});

router.get("/sync/history", authorize('manage_settings'), async (req: Request, res: Response) => {
  try {
    const history = await queryAll("SELECT * FROM processed_emails ORDER BY processed_at DESC LIMIT 50");
    res.json(history);
  } catch (error) {
    console.error("Sync History Error:", error);
    res.status(500).json({ error: "Failed to fetch sync history" });
  }
});

router.post("/notifications/read", authorize('view_dashboard'), async (req: Request, res: Response) => {
  await runQuery("UPDATE notifications SET is_read = 1");
  res.json({ success: true });
});

router.get("/candidates/:candidate_id/attachments", authorize('view_candidates'), async (req: Request, res: Response) => {
  const attachments = await queryAll("SELECT * FROM candidate_attachments WHERE candidate_id = ?", [req.params.candidate_id]);
  res.json(attachments);
});

router.get("/rankings/:job_id", authorize('view_rankings'), async (req: Request, res: Response) => {
  const rankings = await queryAll(`
    SELECT r.*, c.name, c.skills
    FROM rankings r
    JOIN candidates c ON r.candidate_id = c.id
    WHERE r.job_id = ?
    ORDER BY r.match_score DESC
  `, [req.params.job_id]);

  const result = rankings.map((r: any) => ({
    ...r,
    skills: JSON.parse(r.skills || "[]")
  }));
  res.json(result);
});

router.post("/candidates/:candidate_id/chat", authorize('view_candidates'), async (req: Request, res: Response) => {
  const { message } = req.body;
  const candidateId = req.params.candidate_id;

  try {
    const candidate = await queryOne("SELECT resume_text FROM candidates WHERE id = ?", [candidateId]);
    if (!candidate || !candidate.resume_text) {
      return res.status(404).json({ error: "Candidate resume text not found" });
    }

    const result = await chatWithResume(candidate.resume_text, message);
    res.json(result);
  } catch (error) {
    console.error("Chat API Error:", error);
    res.status(500).json({ error: "Chat failed" });
  }
});

export default router;
