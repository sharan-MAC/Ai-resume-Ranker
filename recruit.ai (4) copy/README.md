# Recruit.AI - Intelligent Recruitment Dashboard

A professional, AI-powered recruitment tool for automated resume ingestion, extraction, and candidate ranking.

## Features

- **Automated Ingestion**: Monitors your email for unread resumes (PDF/DOCX).
- **AI Extraction**: Uses Gemini AI to extract skills, experience, and education from resumes.
- **Smart Ranking**: Automatically ranks candidates against job descriptions using AI.
- **Modern UI**: A clean, technical dashboard built with React, Tailwind CSS, and Framer Motion.

## Tech Stack

- **Backend & Frontend**: Python 3.x, FastAPI, Jinja2 Templates.
- **Styling**: Tailwind CSS (CDN).
- **Interactivity**: Alpine.js (CDN).
- **Icons**: Lucide Icons (CDN).
- **Database**: SQLite.
- **AI**: Google Gemini AI (Python SDK).
- **Email**: imap-tools.
- **File Processing**: pypdf, mammoth.

## Getting Started (Local Development)

1. **Clone the repository**.
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables**:
   Create a `.env` file based on `.env.example`.
   ```env
   GEMINI_API_KEY=your_api_key
   EMAIL_USER=your_email@gmail.com
   EMAIL_PASS=your_app_password
   ```
4. **Run the application**:
   ```bash
   python3 main.py
   ```
5. **Open the app**:
   Navigate to `http://localhost:3000`.

## Project Structure

- `main.py`: Main FastAPI server entry point (Python).
- `templates/index.html`: The entire frontend UI (HTML/JS).
- `requirements.txt`: Python dependencies.
- `recruitment.db`: SQLite database file.
