import sqlite3
import os
from app.core.config import settings

def get_db_conn():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            phone TEXT,
            skills TEXT,
            experience_years REAL,
            education TEXT,
            resume_path TEXT,
            parsed_json TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            required_skills TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("""
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
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS finalized_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            candidate_id INTEGER,
            status TEXT DEFAULT 'shortlisted',
            created_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_emails (
            message_id TEXT PRIMARY KEY,
            processed_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidate_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            file_path TEXT,
            file_type TEXT,
            created_at TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            message TEXT,
            type TEXT, -- 'new_resume', 'shortlisted', etc.
            is_read INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    # Initialize default settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_new_job', 'true')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_shortlisted', 'true')")
    conn.commit()
    conn.close()
