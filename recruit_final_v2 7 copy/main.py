import uvicorn
from app.main import app

if __name__ == "__main__":
    print("Starting Recruit.AI Python Backend on port 3000...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
    except Exception as e:
        print(f"Server failed to start: {e}")
