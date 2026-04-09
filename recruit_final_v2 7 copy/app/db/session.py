import sqlite3
import hashlib
import datetime
from pathlib import Path
from app.core.config import settings


def get_db_conn():
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def init_db():
    conn = get_db_conn()
    c = conn.cursor()

    # Create tables (won't overwrite existing)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT DEFAULT 'recruiter',
            created_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT,
            email            TEXT,
            phone            TEXT DEFAULT '',
            skills           TEXT DEFAULT '[]',
            experience_years REAL DEFAULT 0,
            education        TEXT DEFAULT '',
            resume_path      TEXT UNIQUE,
            parsed_json      TEXT DEFAULT '{}',
            ai_enriched      INTEGER DEFAULT 0,
            created_at       TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT,
            description     TEXT,
            required_skills TEXT DEFAULT '[]',
            created_at      TEXT
        );
        CREATE TABLE IF NOT EXISTS rankings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id           INTEGER,
            candidate_id     INTEGER,
            match_score      REAL DEFAULT 0,
            analysis_summary TEXT DEFAULT '',
            created_at       TEXT,
            UNIQUE(job_id, candidate_id)
        );
        CREATE TABLE IF NOT EXISTS finalized_candidates (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id       INTEGER,
            candidate_id INTEGER,
            status       TEXT DEFAULT 'Shortlisted',
            created_at   TEXT,
            UNIQUE(job_id, candidate_id)
        );
        CREATE TABLE IF NOT EXISTS processed_emails (
            message_id   TEXT PRIMARY KEY,
            processed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS candidate_attachments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            file_path    TEXT,
            file_type    TEXT DEFAULT 'resume',
            created_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT,
            message    TEXT,
            type       TEXT DEFAULT 'info',
            is_read    INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # ── Migrations for existing DBs ──────────────────────────────
    # Add ai_enriched column if missing
    c.execute("PRAGMA table_info(candidates)")
    cols = {row["name"] for row in c.fetchall()}
    if "ai_enriched" not in cols:
        c.execute("ALTER TABLE candidates ADD COLUMN ai_enriched INTEGER DEFAULT 0")
        print("✅ Migration: added ai_enriched column")

    # Ensure UNIQUE index on rankings
    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_rankings_unique
          ON rankings(job_id, candidate_id)
    """)

    # ── Default settings ─────────────────────────────────────────
    defaults = [
        ("notify_new_job",       "true"),
        ("notify_shortlisted",   "true"),
        ("notify_new_candidate", "true"),
        ("shortlist_threshold",  "75"),
        ("hr_email",             settings.HR_EMAIL or ""),
        ("last_sync_at",         ""),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # ── Default admin user ────────────────────────────────────────
    c.execute("SELECT 1 FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin123"), "admin", datetime.datetime.now().isoformat())
        )
        print("✅ Default admin created: admin / admin123")

    conn.commit()
    conn.close()
    print("✅ Database ready")
