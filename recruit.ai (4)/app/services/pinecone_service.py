import os
from app.core.config import settings

try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    print("Pinecone client not found. Semantic search will be disabled.")

pc = None
index = None

import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=3)

def _get_pinecone_index_sync():
    global pc, index
    if index:
        return index
    
    if not PINECONE_AVAILABLE or not settings.PINECONE_API_KEY:
        return None
        
    try:
        if not pc:
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        
        # Create index if it doesn't exist
        if settings.PINECONE_INDEX_NAME not in pc.list_indexes().names():
            pc.create_index(
                name=settings.PINECONE_INDEX_NAME,
                dimension=768, # Dimension for gemini-embedding-2-preview
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
        
        index = pc.Index(settings.PINECONE_INDEX_NAME)
        return index
    except Exception as e:
        print(f"Pinecone Initialization Error: {e}")
        return None

async def get_pinecone_index():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _get_pinecone_index_sync)

async def upsert_candidate_vector(candidate_id: int, embedding: list, metadata: dict):
    idx = await get_pinecone_index()
    if not idx:
        return False
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, lambda: idx.upsert(
            vectors=[
                {
                    "id": str(candidate_id),
                    "values": embedding,
                    "metadata": metadata
                }
            ]
        ))
        return True
    except Exception as e:
        print(f"Pinecone Upsert Error: {e}")
        return False

async def query_candidates(embedding: list, top_k: int = 10):
    idx = await get_pinecone_index()
    if not idx:
        return []
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(executor, lambda: idx.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True
        ))
        return results.matches
    except Exception as e:
        print(f"Pinecone Query Error: {e}")
        return []
