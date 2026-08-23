"""Resolve a meeting video into a local file, whatever form it started in."""
from __future__ import annotations

from pathlib import Path

from civiclens.config import MEDIA_DIR


def resolve_video(source: str, dest_name: str) -> Path:
    """
    source: a local file path, a direct video URL, or a YouTube/Granicus-style URL.
    dest_name: filename (no extension needed) to save into MEDIA_DIR.
    """
    local = Path(source)
    if local.exists():
        return local

    if source.startswith("http"):
        return _download(source, dest_name)

    raise FileNotFoundError(f"Video source not found and not a URL: {source}")


def _download(url: str, dest_name: str) -> Path:
    dest = MEDIA_DIR / f"{dest_name}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if "youtube.com" in url or "youtu.be" in url:
        import yt_dlp

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
