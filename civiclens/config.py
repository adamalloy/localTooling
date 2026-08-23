"""Central configuration. Values come from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CIVICLENS_DATA_DIR", BASE_DIR / "data"))
MEDIA_DIR = DATA_DIR / "media"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
DOCUMENTS_DIR = DATA_DIR / "documents"
UPLOADS_DIR = DATA_DIR / "uploads"

for d in (DATA_DIR, MEDIA_DIR, TRANSCRIPTS_DIR, DOCUMENTS_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("CIVICLENS_DATABASE_URL", f"sqlite:///{DATA_DIR / 'civiclens.db'}")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANALYSIS_MODEL = os.environ.get("CIVICLENS_ANALYSIS_MODEL", "claude-opus-5")

# Whisper model size: tiny/base/small/medium/large-v2/large-v3. Larger = more accurate, slower.
WHISPER_MODEL_SIZE = os.environ.get("CIVICLENS_WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("CIVICLENS_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("CIVICLENS_WHISPER_COMPUTE_TYPE", "int8")

# Required to download pyannote's speaker-diarization pipeline from Hugging Face.
# Get one at https://huggingface.co/settings/tokens and accept the model's terms at
# https://huggingface.co/pyannote/speaker-diarization-3.1
HUGGINGFACE_TOKEN = os.environ.get("HUGGINGFACE_TOKEN")

# Legistar Web API client name. Oakland runs on Legistar; verify the exact client
# slug against https://webapi.legistar.com/v1/{client}/bodies before relying on it —
# this default is unverified against the live site (see README "Data sources" note).
LEGISTAR_CLIENT = os.environ.get("CIVICLENS_LEGISTAR_CLIENT", "oakland")
LEGISTAR_API_BASE = f"https://webapi.legistar.com/v1/{LEGISTAR_CLIENT}"
