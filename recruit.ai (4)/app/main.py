import os
import datetime
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio

from app.db.session import init_db
from app.api.endpoints import router as api_router
from app.core.worker import auto_ingest_worker
from app.core.notifications import manager
from fastapi import WebSocket, WebSocketDisconnect

def create_app() -> FastAPI:
    app = FastAPI(title="Recruit.AI API")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # WebSocket Endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                # Keep connection alive
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # Health Check
    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

    @app.on_event("startup")
    async def startup_event():
        print("Initializing Database...")
        try:
            init_db()
        except Exception as e:
            print(f"Database Initialization Failed: {e}")
            
        # Start the background worker
        print("Starting background worker...")
        asyncio.create_task(auto_ingest_worker())

    # Include API Routes
    app.include_router(api_router, prefix="/api")

    # Templates and Static Files
    templates = Jinja2Templates(directory="templates")

    if os.path.exists("dist"):
        app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

    # Mount resumes_raw for file access
    resumes_dir = Path("resumes_raw")
    resumes_dir.mkdir(exist_ok=True)
    app.mount("/resumes_raw", StaticFiles(directory=str(resumes_dir)), name="resumes_raw")

    @app.get("/")
    async def serve_home(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API route not found")
        
        file_path = Path("dist") / full_path
        if file_path.is_file():
            from fastapi.responses import FileResponse
            return FileResponse(file_path)
            
        return templates.TemplateResponse("index.html", {"request": request})

    return app

app = create_app()
