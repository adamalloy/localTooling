"""
Local audio extraction + transcription for scripts/transcribe_media.py.

Deliberately independent from civiclens's version of this (same idea, different
tool) — the two are meant to stay splittable into separate repos, not share
internals. No speaker diarization here: presentation/pitch videos are typically
single-narrator, and proposed-idea extraction works fine off plain transcript text.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from biopunk_media.config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_SIZE


def extract_audio(video_path: Path, out_path: Path, sample_rate: int = 16000) -> Path:
    """Extract mono PCM WAV audio from a video (or re-encode an audio file) via ffmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ac", "1", "-ar", str(sample_rate), "-vn",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed to extract audio from {video_path}:\n{result.stderr}")
    return out_path


def transcribe_audio(audio_path: Path) -> str:
    """Run faster-whisper locally over the audio file and return the full transcript text."""
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments, _info = model.transcribe(str(audio_path), vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()
