"""
Single-container entrypoint for hosting (Coolify / any Docker host).

  /api/...   -> the FastAPI scorer in api/main.py (live model, live attack simulation)
  /          -> the built React demo from web/dist (falls back to snapshots only if /api is down)

    uvicorn api.serve:app --host 0.0.0.0 --port 8000
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.main import app as api_app

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"

app = FastAPI(title="Second Thought", docs_url=None, redoc_url=None)
app.mount("/api", api_app)
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="web")
