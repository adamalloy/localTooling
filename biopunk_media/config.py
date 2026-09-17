"""Central configuration. Values come from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BIOPUNK_MEDIA_DATA_DIR", BASE_DIR / "data" / "biopunk"))
UPLOADS_DIR = DATA_DIR / "uploads"
VIDEOS_DIR = UPLOADS_DIR / "videos"

for d in (DATA_DIR, UPLOADS_DIR, VIDEOS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "BIOPUNK_MEDIA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'biopunk_media.db'}"
)

# Shared with civiclens — one Anthropic key for the whole repo.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANALYSIS_MODEL = os.environ.get("BIOPUNK_MEDIA_ANALYSIS_MODEL", "claude-opus-5")

# Only used by scripts/transcribe_media.py (the optional local-Whisper path).
WHISPER_MODEL_SIZE = os.environ.get("BIOPUNK_MEDIA_WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("BIOPUNK_MEDIA_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("BIOPUNK_MEDIA_WHISPER_COMPUTE_TYPE", "int8")
