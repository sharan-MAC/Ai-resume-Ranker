"""Auto-ingest worker — kept for backward compatibility, actual polling is in main.py"""
import asyncio
from app.services.email_service import perform_ingestion

async def auto_ingest_worker():
    """Legacy worker — main.py handles polling now."""
    await asyncio.sleep(60)  # defer to main.py's _auto_poll
