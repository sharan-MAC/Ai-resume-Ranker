import sqlite3 from 'sqlite3';
import { settings } from '../core/config';
import { promisify } from 'util';

export const getDbConn = () => {
  const db = new sqlite3.Database(settings.DB_PATH);
  return db;
};

export const initDb = async () => {
  const db = getDbConn();

  const run = async (sql: string, params: any[] = []) => {
    return new Promise((resolve, reject) => {
      db.run(sql, params, (err) => {
        if (err) reject(err);
        else resolve(true);
      });
    });
  };

  await run(`
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        phone TEXT,
        skills TEXT,
        experience_years REAL,
        education TEXT,
        resume_path TEXT,
        resume_text TEXT,
        parsed_json TEXT,
        created_at TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        required_skills TEXT,
        created_at TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS rankings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        candidate_id INTEGER,
        match_score REAL,
        rank_position INTEGER,
        analysis_summary TEXT,
        created_at TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        FOREIGN KEY(candidate_id) REFERENCES candidates(id)
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS finalized_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        candidate_id INTEGER,
        status TEXT DEFAULT 'shortlisted',
        created_at TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        FOREIGN KEY(candidate_id) REFERENCES candidates(id)
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS processed_emails (
        message_id TEXT PRIMARY KEY,
        processed_at TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS candidate_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER,
        file_path TEXT,
        file_type TEXT,
        created_at TEXT,
        FOREIGN KEY(candidate_id) REFERENCES candidates(id)
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        message TEXT,
        type TEXT, -- 'new_resume', 'shortlisted', etc.
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        action TEXT,
        details TEXT,
        created_at TEXT
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT, -- 'admin', 'recruiter', 'hiring_manager'
        created_at TEXT
    )
  `);

  // Initialize default users
  const now = new Date().toISOString();
  const bcrypt = await import('bcryptjs');
  const adminHash = await bcrypt.hash('admin123', 10);
  const recruiterHash = await bcrypt.hash('recruiter123', 10);
  const managerHash = await bcrypt.hash('manager123', 10);

  await run("INSERT OR IGNORE INTO users (username, password, role, created_at) VALUES ('admin', ?, 'admin', ?)", [adminHash, now]);
  await run("INSERT OR IGNORE INTO users (username, password, role, created_at) VALUES ('recruiter', ?, 'recruiter', ?)", [recruiterHash, now]);
  await run("INSERT OR IGNORE INTO users (username, password, role, created_at) VALUES ('manager', ?, 'hiring_manager', ?)", [managerHash, now]);

  // Initialize default settings
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_new_job', 'true')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_shortlisted', 'true')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('email_ingestion_limit', '5')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('ai_model', 'gemini-3-flash-preview')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('ai_temperature', '0.7')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('accent_color', 'emerald')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('ignore_keywords', '')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('hr_email', 'sharanrh297@gmail.com')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_new_candidate', 'true')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('email_notifications', 'true')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('system_notifications', 'true')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('disable_manual_upload', 'false')");
  await run("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_sync_at', '')");

  db.close();
};

export const queryAll = (sql: string, params: any[] = []): Promise<any[]> => {
  const db = getDbConn();
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      db.close();
      if (err) reject(err);
      else resolve(rows);
    });
  });
};

export const queryOne = (sql: string, params: any[] = []): Promise<any> => {
  const db = getDbConn();
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => {
      db.close();
      if (err) reject(err);
      else resolve(row);
    });
  });
};

export const runQuery = (sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> => {
  const db = getDbConn();
  return new Promise((resolve, reject) => {
    db.run(sql, params, function(err) {
      db.close();
      if (err) reject(err);
      else resolve({ lastID: this.lastID, changes: this.changes });
    });
  });
};

export const getSetting = async (key: string, defaultValue: string = ''): Promise<string> => {
  try {
    const row = await queryOne("SELECT value FROM settings WHERE key = ?", [key]);
    return row ? row.value : defaultValue;
  } catch (error) {
    console.error(`Error fetching setting ${key}:`, error);
    return defaultValue;
  }
};
