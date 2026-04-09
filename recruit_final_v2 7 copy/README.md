# Recruit.AI — Intelligent Recruitment Platform

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run
python main.py
# OR
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Open: http://localhost:3000  
**Default login:** `admin` / `admin123`

---

## 🔧 Configuration (.env)

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key for AI parsing & ranking |
| `EMAIL_USER` | Gmail address that receives resumes (AI mailbox) |
| `EMAIL_PASS` | **Gmail App Password** (not your real password!) |
| `HR_EMAIL` | HR email address — receives shortlist notifications |
| `PINECONE_API_KEY` | Pinecone vector DB for semantic search |
| `PINECONE_INDEX_NAME` | Pinecone index name |

## ⚠️ Gmail App Password Setup

Google blocks direct password login. You must use an App Password:

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Security → 2-Step Verification (enable if not already)
3. Security → App Passwords
4. Select "Mail" → "Other" → name it "Recruit.AI"
5. Copy the 16-character password into `EMAIL_PASS` in `.env`

## 📧 How Email Ingestion Works

1. HR sends an email with resume PDF/DOCX attached to `scrh2k23@gmail.com`
2. The app checks this inbox every **60 seconds** automatically
3. All unread emails with `.pdf` or `.docx` attachments are processed
4. AI (Gemini) extracts candidate data and auto-ranks against all jobs
5. Candidates appear instantly in the dashboard

## 🐛 Fixes Applied (v2.0)

- ✅ Fixed wrong Gemini model name (`gemini-3-flash-preview` → `gemini-1.5-flash`)
- ✅ Added `/api/login` endpoint (was completely missing)
- ✅ Added `users` table with default `admin / admin123` account
- ✅ Fixed IMAP — now fetches ALL unread emails with attachments (not just from one sender)
- ✅ Fixed `imap_tools.flag()` syntax bug
- ✅ Added missing endpoints: `/api/system/health`, `/api/activities`, `/api/sync/history`, `/api/test/email`, `/api/candidates/{id}/chat`
- ✅ Added `DELETE /api/candidates/{id}` and `DELETE /api/jobs/{id}`
- ✅ Added `/api/chat` for general AI assistant
- ✅ Cleaned up requirements.txt with correct package names
- ✅ Fixed `app/main.py` startup sequence

## 📁 Project Structure

```
recruit_ai/
├── app/
│   ├── api/endpoints.py      # All REST API routes
│   ├── core/
│   │   ├── config.py         # Settings from .env
│   │   ├── notifications.py  # WebSocket manager
│   │   └── worker.py         # Background email poller
│   ├── db/session.py         # SQLite DB + init
│   ├── models/schemas.py     # Pydantic models
│   └── services/
│       ├── ai_service.py     # Gemini AI integration
│       ├── email_service.py  # IMAP email fetching
│       ├── pinecone_service.py # Vector search
│       └── resume_processor.py # Resume parsing pipeline
├── templates/index.html      # Frontend (Alpine.js)
├── resumes_raw/              # Saved resume files
├── recruitment.db            # SQLite database
├── .env                      # Credentials
├── requirements.txt
└── main.py                   # Entry point
```
