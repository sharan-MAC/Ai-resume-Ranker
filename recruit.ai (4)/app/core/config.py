import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Recruit.AI"
    DB_PATH: str = "recruitment.db"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "recruit-ai")
    EMAIL_USER: str = os.getenv("EMAIL_USER")
    EMAIL_PASS: str = os.getenv("EMAIL_PASS")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "imap.gmail.com")
    HR_EMAIL: str = os.getenv("HR_EMAIL", "sharanrh297@gmail.com")

settings = Settings()
