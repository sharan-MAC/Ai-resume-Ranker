import datetime
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.db.session import init_db
from app.api.endpoints import router as api_router
from app.core.notifications import manager

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(title="Recruit.AI", version="4.0.0")

    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.get("/api/health")
    async def health():
        return {"status": "healthy", "time": datetime.datetime.now().isoformat()}

    @app.on_event("startup")
    async def startup():
        print("\n" + "="*55)
        print("  🚀 Recruit.AI v4.0 Starting...")
        print("="*55)
        init_db()

        # Mount resumes dir AFTER init
        resumes_dir = BASE_DIR / "resumes_raw"
        resumes_dir.mkdir(exist_ok=True)

        # Run startup tasks
        asyncio.create_task(_startup_tasks())

        print("✅ Server ready: http://localhost:3000  (or your configured port)")
        print("   Login: admin / admin123")
        print("="*55 + "\n")

    app.include_router(api_router, prefix="/api")

    # Serve resume files
    resumes_dir = BASE_DIR / "resumes_raw"
    resumes_dir.mkdir(exist_ok=True)
    app.mount("/resumes_raw", StaticFiles(directory=str(resumes_dir)), name="resumes_raw")

    # Serve frontend
    templates_dir = BASE_DIR / "templates"
    templates_dir.mkdir(exist_ok=True)
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/")
    async def home(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/{full_path:path}")
    async def spa(request: Request, full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(404, "API route not found")
        return templates.TemplateResponse("index.html", {"request": request})

    return app


async def _startup_tasks():
    """Run after server is ready."""
    await asyncio.sleep(1)

    # Fast-rank all existing candidates vs all jobs immediately
    try:
        from app.api.endpoints import _fast_skill_rank_job
        from app.db.session import get_db_conn
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM jobs")
        jobs = cursor.fetchall()
        conn.close()
        if jobs:
            print(f"[Startup] Fast-ranking all candidates for {len(jobs)} job(s)...")
            for job in jobs:
                await _fast_skill_rank_job(job["id"])
            print(f"[Startup] ✅ Fast ranking complete")
        else:
            print(f"[Startup] No jobs yet — create jobs to start ranking")
    except Exception as e:
        print(f"[Startup] Fast rank error: {e}")

    # Start auto-polling Gmail every 60 seconds
    asyncio.create_task(_auto_poll_gmail())
    print(f"[Startup] 📧 Gmail auto-poll started (every 60 seconds)")


async def _auto_poll_gmail():
    """Poll Gmail every 60 seconds for new resumes."""
    from app.services.email_service import perform_ingestion
    from app.db.session import get_db_conn
    print("[AutoPoll] Gmail polling active")
    while True:
        await asyncio.sleep(60)
        try:
            result = await perform_ingestion()
            if result.get("processedCount", 0) > 0:
                print(f"[AutoPoll] ✅ {result['message']}")
                conn = get_db_conn()
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync_at', ?)",
                    (datetime.datetime.now().isoformat(),)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[AutoPoll] Error: {e}")


app = create_app()
