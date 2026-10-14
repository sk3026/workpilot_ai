from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router

app = FastAPI(title="WorkPilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"

if ASSETS_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(ASSETS_DIR)),
        name="assets",
    )


@app.get("/", include_in_schema=False)
async def serve_frontend():
    index_file = FRONTEND_DIST / "index.html"

    if index_file.is_file():
        return FileResponse(index_file)

    return {
        "message": "WorkPilot API is running",
        "docs": "/docs",
        "frontend": "Build not found",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_file = FRONTEND_DIST / "favicon.ico"

    if favicon_file.is_file():
        return FileResponse(favicon_file)

    raise HTTPException(status_code=404, detail="Favicon not found")
