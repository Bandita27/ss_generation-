from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.router import extraction


app = FastAPI(title="Video to Crop Extraction API", version="0.3.0")

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage_dir = Path(settings.STORAGE_ROOT)
storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")

app.include_router(extraction.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "video-crop-extraction"}