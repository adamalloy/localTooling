"""Extract paragraph text from a .docx transcript export (e.g. from an audio transcription tool)."""
from __future__ import annotations

from pathlib import Path


def extract_docx_paragraphs(path: Path) -> list[str]:
    import docx

    document = docx.Document(str(path))
    return [p.text for p in document.paragraphs if p.text.strip()]
