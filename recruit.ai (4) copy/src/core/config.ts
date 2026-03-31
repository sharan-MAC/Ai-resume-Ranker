import dotenv from 'dotenv';
dotenv.config();

export const settings = {
  PROJECT_NAME: "Recruit.AI",
  DB_PATH: "recruitment.db",
  GEMINI_API_KEY: process.env.GEMINI_API_KEY,
  PINECONE_API_KEY: process.env.PINECONE_API_KEY,
  PINECONE_INDEX_NAME: process.env.PINECONE_INDEX_NAME || "recruit-ai",
  EMAIL_USER: process.env.EMAIL_USER,
  EMAIL_PASS: process.env.EMAIL_PASS,
  SMTP_HOST: process.env.SMTP_HOST || "smtp.gmail.com",
  SMTP_PORT: parseInt(process.env.SMTP_PORT || "587"),
  EMAIL_HOST: process.env.EMAIL_HOST || "imap.gmail.com",
  EMAIL_PORT: parseInt(process.env.EMAIL_PORT || "993"),
  HR_EMAIL: process.env.HR_EMAIL || "sharanrh297@gmail.com",
};
