"""
Run this ONCE to migrate your existing recruitment.db:
  python migrate_db.py
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "recruitment.db"
conn = sqlite3.connect(str(DB))
c = conn.cursor()

# Add ai_enriched column if missing
try:
    c.execute("ALTER TABLE candidates ADD COLUMN ai_enriched INTEGER DEFAULT 0")
    print("Added ai_enriched column")
except:
    print("ai_enriched already exists")

# Add resume_path UNIQUE if missing (recreate if needed)
# Just ensure old duplicates are cleaned up
c.execute("""
    DELETE FROM candidates WHERE rowid NOT IN (
        SELECT MIN(rowid) FROM candidates GROUP BY email
    ) AND email != ''
""")
print(f"Cleaned {conn.total_changes} duplicate email rows")

# Mark all existing candidates as NOT ai_enriched (so they get re-ranked)
c.execute("UPDATE candidates SET ai_enriched=0 WHERE ai_enriched IS NULL OR ai_enriched=''")

# Create UNIQUE index on rankings if not exists
try:
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rankings_unique ON rankings(job_id, candidate_id)")
    print("Created unique index on rankings")
except Exception as e:
    print(f"Rankings index: {e}")

conn.commit()
conn.close()
print("Migration complete!")
