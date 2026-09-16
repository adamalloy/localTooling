"""Central configuration. Values come from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BIOPUNK_MEDIA_DATA_DIR", BASE_DIR / "data" / "biopunk"))
UPLOADS_DIR = DATA_DIR / "uploads"

for d in (DATA_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "BIOPUNK_MEDIA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'biopunk_media.db'}"
)
