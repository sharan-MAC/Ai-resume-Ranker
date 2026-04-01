import asyncio
from app.services.email_service import perform_ingestion, HR_SENDER_EMAIL

async def auto_ingest_worker():
    """Background worker that polls the AI mailbox every 60 seconds."""
    print(f"Starting background ingestion worker... Monitoring {HR_SENDER_EMAIL}")
    while True:
        try:
            await perform_ingestion()
        except Exception as e:
            print(f"Background Ingestion Error: {e}")
        await asyncio.sleep(60)
