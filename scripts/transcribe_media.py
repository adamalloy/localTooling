#!/usr/bin/env python3
"""
Generate a transcript for a MediaAsset using local Whisper (no audio leaves your
machine). Runs as a script rather than through the web app because transcription
of a long video can take minutes — you don't want a browser tab hanging on it.

Requires the video extras: pip install -r requirements-biopunk-media-video.txt
Also requires ffmpeg on your PATH.

Usage:
    python scripts/transcribe_media.py --media-id 3
    python scripts/transcribe_media.py --all-pending   # every asset with no transcript yet
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biopunk_media.config import UPLOADS_DIR
from biopunk_media.db import init_db, session_scope
from biopunk_media.ingestion.transcribe import extract_audio, transcribe_audio
from biopunk_media.ingestion.video_source import resolve_source
from biopunk_media.models import MediaAsset, TranscriptSource, TranscriptStatus


def transcribe_one(media_id: int) -> None:
    with session_scope() as session:
        asset = session.get(MediaAsset, media_id)
        if asset is None:
            print(f"No media asset with id {media_id}")
            return

        asset.transcript_status = TranscriptStatus.PENDING
        session.flush()

        local_path = UPLOADS_DIR / asset.file_path if asset.file_path else Path("/nonexistent")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                video_path = resolve_source(asset.external_url, local_path, f"media-{media_id}")
                audio_path = extract_audio(video_path, Path(tmp) / "audio.wav")
                text = transcribe_audio(audio_path)
            asset.transcript_text = text
            asset.transcript_source = TranscriptSource.GENERATED
            asset.transcript_status = TranscriptStatus.READY
            print(f"[{media_id}] transcribed ({len(text)} chars): {asset.title}")
        except Exception as e:
            asset.transcript_status = TranscriptStatus.FAILED
            print(f"[{media_id}] FAILED: {asset.title} — {e}")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--media-id", type=int, help="Transcribe a single MediaAsset by id.")
    group.add_argument(
        "--all-pending", action="store_true",
        help="Transcribe every MediaAsset with transcript_status NONE or FAILED.",
    )
    args = parser.parse_args()

    init_db()

    if args.media_id:
        transcribe_one(args.media_id)
        return

    with session_scope() as session:
        ids = [
            a.id for a in session.query(MediaAsset).all()
            if a.transcript_status in (TranscriptStatus.NONE, TranscriptStatus.FAILED)
        ]
    if not ids:
        print("Nothing pending.")
        return
    for media_id in ids:
        transcribe_one(media_id)


if __name__ == "__main__":
    main()
