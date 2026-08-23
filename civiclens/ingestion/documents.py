"""Fetch and parse budgets, reports, policies, minutes, and agendas into Document rows."""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from civiclens.config import DOCUMENTS_DIR
from civiclens.models import Document, DocumentType


def _download(url: str) -> Path:
    dest = DOCUMENTS_DIR / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.pdf"
    if dest.exists():
        return dest
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def _parse_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def ingest_document(
    session: Session,
    city_id: int,
    title: str,
    source_url: str,
    doc_type: DocumentType,
    meeting_id: int | None = None,
    published_date: dt.date | None = None,
) -> Document:
    local_path = None
    parsed_text = None
    if source_url.lower().endswith(".pdf"):
        local_path = _download(source_url)
        parsed_text = _parse_pdf_text(local_path)
    else:
        resp = requests.get(source_url, timeout=60)
        resp.raise_for_status()
        parsed_text = resp.text

    doc = Document(
        city_id=city_id,
        meeting_id=meeting_id,
        doc_type=doc_type,
        title=title,
        source_url=source_url,
        local_path=str(local_path) if local_path else None,
        published_date=published_date,
        parsed_text=parsed_text,
    )
    session.add(doc)
    session.flush()
    return doc
