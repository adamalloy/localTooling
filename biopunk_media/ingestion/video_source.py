"""Resolve a MediaAsset's source (local upload or external URL) to a local file
for transcription. Only reached by scripts/transcribe_media.py."""
from __future__ import annotations

from pathlib import Path

from biopunk_media.config import VIDEOS_DIR


def resolve_source(external_url: str | None, local_path: Path, dest_name: str) -> Path:
    """
    local_path: the already-resolved local file, if this asset was an upload.
    external_url: used only if local_path doesn't exist — downloaded into VIDEOS_DIR.
    """
    if local_path.exists():
        return local_path
    if not external_url:
        raise FileNotFoundError(f"No local file at {local_path} and no external_url to fall back to.")
    return _download(external_url, dest_name)


def _download(url: str, dest_name: str) -> Path:
    dest = VIDEOS_DIR / f"{dest_name}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if "youtube.com" in url or "youtu.be" in url:
        try:
            import yt_dlp
        except ImportError as e:
            raise RuntimeError(
                "This is a YouTube link — install yt-dlp to transcribe it "
                "(pip install yt-dlp) or paste a transcript instead."
            ) from e
        ydl_opts = {"outtmpl": str(dest.with_suffix("")) + ".%(ext)s", "format": "bestvideo+bestaudio/best"}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        matches = list(dest.parent.glob(f"{dest.stem}.*"))
        if not matches:
            raise RuntimeError(f"yt-dlp reported success but no output file found for {url}")
        return matches[0]

    import requests

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest
