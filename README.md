# Recruit.AI---Intelligent-Recruitment-Dashboard
A professional, AI-powered recruitment tool for automated resume ingestion, extraction, and candidate ranking.
Overview

This project is an end-to-end AI-powered recruitment automation platform that ingests resumes from email, extracts structured candidate information using Google Gemini AI, and ranks applicants against job descriptions. It provides a clean and responsive dashboard for efficient candidate evaluation.

Features
Automated Resume Ingestion

Monitors email inbox using IMAP

Fetches unread resumes automatically

Supports PDF and DOCX formats

AI-Based Resume Parsing

Uses Google Gemini AI for information extraction

Extracts:

Skills

Work experience

Education

Projects (if available)

Handles unstructured resume data

Candidate Ranking System

Matches candidate profiles with job descriptions

Generates AI-based relevance scores

Ranks candidates automatically

Dashboard Interface

Clean and responsive UI

Displays candidate insights and rankings

Smooth interactions using lightweight frontend tools

Tech Stack
Backend

Python 3.x

FastAPI

Jinja2 Templates

Frontend

Tailwind CSS (CDN)

Alpine.js (CDN)

Database

SQLite

AI Integration

Google Gemini AI (Python SDK)

Email Integration

imap-tools

File Processing

pypdf (PDF parsing)

mammoth (DOCX parsing)

Icons

Lucide Icons

Project Structure
├── main.py                # FastAPI application entry point
├── templates/
│   └── index.html        # Frontend UI
├── recruitment.db        # SQLite database
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
└── README.md             # Documentation
Getting Started (Local Development)
1. Clone the Repository
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
2. Install Dependencies
pip install -r requirements.txt
3. Configure Environment Variables

Create a .env file:

GEMINI_API_KEY=your_api_key

EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_gmail_app_password

EMAIL_HOST=imap.gmail.com
EMAIL_PORT=993

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

HR_EMAIL=hr@company.com

DATABASE_URL=sqlite:///./recruitment.db

Note:

Use a Gmail App Password instead of your actual password.

4. Run the Application
python3 main.py
5. Access the Application

Open the following URL in your browser:

http://localhost:3000
Deployment (Render)
Steps

Create a new Web Service on Render

Connect your GitHub repository

Select Python environment

Build Command
pip install -r requirements.txt
Start Command
uvicorn main:app --host 0.0.0.0 --port $PORT
Required Environment Variables

GEMINI_API_KEY

EMAIL_USER

EMAIL_PASS

EMAIL_HOST=imap.gmail.com

EMAIL_PORT=993

SMTP_HOST=smtp.gmail.com

SMTP_PORT=587

HR_EMAIL

DATABASE_URL=sqlite:///./recruitment.db

System Workflow

The system monitors the email inbox

New resumes are downloaded automatically

Gemini AI extracts structured information

Candidate data is matched with job descriptions

Candidates are ranked based on relevance

Results are displayed in the dashboard

Security Considerations

Use environment variables to store sensitive data

Do not commit .env files to version control

Use app-specific passwords for email authentication

Enable HTTPS in production deployments

Future Enhancements

Advanced filtering and search capabilities

Explainable AI for scoring transparency

Automated candidate email responses

Multi-user authentication system

Analytics dashboard for HR insights

Contributing

Fork the repository

Create a new branch

Commit your changes

Submit a pull request

License

This project is licensed under the MIT License.
