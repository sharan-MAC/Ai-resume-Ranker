# 🚀 Recruit.AI — Intelligent Recruitment Dashboard

<div align="center">

![Python](https://img.shields.io/badge/Python-3.x-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green?style=for-the-badge&logo=fastapi)
![SQLite](https://img.shields.io/badge/SQLite-Database-lightblue?style=for-the-badge&logo=sqlite)
![Gemini AI](https://img.shields.io/badge/Google-Gemini_AI-orange?style=for-the-badge&logo=google)
![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-Frontend-cyan?style=for-the-badge&logo=tailwind-css)
![License](https://img.shields.io/badge/License-MIT-red?style=for-the-badge)

### 💼 Professional AI-Powered Recruitment Automation Platform

### Resume Ingestion • AI Extraction • Candidate Ranking • Smart Dashboard

</div>

---

# 📌 Overview

**Recruit.AI** is a complete end-to-end AI-powered recruitment automation system designed to simplify and accelerate the hiring process.

The platform automatically fetches resumes from email inboxes, extracts structured candidate information using **Google Gemini AI**, compares applicants against job descriptions, and ranks candidates based on relevance.

It provides recruiters and HR teams with a clean, responsive, and professional dashboard for faster and smarter hiring decisions.

---

# ✨ Key Features

## 📥 1. Automated Resume Ingestion

### Supports:

- ✔ Email Inbox Monitoring using IMAP  
- ✔ Automatic Fetching of Unread Resumes  
- ✔ PDF Resume Support  
- ✔ DOCX Resume Support  
- ✔ Zero Manual Resume Upload  

---

## 🤖 2. AI-Based Resume Parsing

Powered by **Google Gemini AI**

### Extracted Information:

- ✔ Skills  
- ✔ Work Experience  
- ✔ Education  
- ✔ Projects  
- ✔ Certifications  
- ✔ Candidate Summary  

### Smart Parsing:

Handles both:

- Structured resumes  
- Unstructured resumes  

with high efficiency and accuracy.

---

## 🏆 3. Candidate Ranking System

### Features:

- ✔ JD Matching  
- ✔ AI-Based Relevance Scoring  
- ✔ Automatic Candidate Ranking  
- ✔ Top Applicant Identification  

### Benefits:

- Reduces screening effort  
- Improves hiring speed  
- Helps shortlist better candidates  

---

## 📊 4. Professional Dashboard Interface

### Includes:

- ✔ Clean UI  
- ✔ Fully Responsive Design  
- ✔ Lightweight Frontend  
- ✔ Fast Performance  
- ✔ Candidate Insights  
- ✔ Ranking Visualization  

Built for recruiters to work faster with better visibility.

---

# 🛠 Tech Stack

## Backend

- Python 3.x  
- FastAPI  
- Jinja2 Templates  

## Frontend

- Tailwind CSS (CDN)  
- Alpine.js (CDN)  

## Database

- SQLite  

## AI Integration

- Google Gemini AI (Python SDK)  

## Email Integration

- imap-tools  

## File Processing

- pypdf (PDF parsing)  
- mammoth (DOCX parsing)  

## Icons

- Lucide Icons  

---

# 📁 Project Structure

```bash
Recruit.AI/
│
├── main.py
│   # FastAPI application entry point
│
├── templates/
│   └── index.html
│       # Frontend dashboard UI
│
├── recruitment.db
│   # SQLite database
│
├── requirements.txt
│   # Python dependencies
│
├── .env.example
│   # Environment variables template
│
└── README.md
    # Project documentation
