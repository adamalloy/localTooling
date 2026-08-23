"""End-to-end: video/audio source -> transcript -> diarized Statement rows in the DB."""
from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from civiclens.config import TRANSCRIPTS_DIR
from civiclens.ingestion.transcribe import (
    diarize_audio,
    extract_audio,
    merge_transcript_and_diarization,
    transcribe_audio,
)
from civiclens.ingestion.docx_transcript import extract_docx_paragraphs
from civiclens.ingestion.video_source import resolve_video
from civiclens.models import City, Meeting, Official, Speaker, SpeakerType, Statement, TranscriptStatus

log = logging.getLogger(__name__)

# Heuristic only: suggests a name for an unlabeled speaker turn when someone
# self-introduces during public comment. Always surfaced for human confirmation
# in the web UI before it's attached to a Speaker record — never auto-applied.
_SELF_INTRO_RE = re.compile(
    r"\bmy name is ([A-Z][a-zA-Z'\-]+(?: [A-Z][a-zA-Z'\-]+){0,2})\b"
)


def suggest_speaker_name(text: str) -> str | None:
    m = _SELF_INTRO_RE.search(text)
    return m.group(1) if m else None


def ingest_meeting(
    session: Session,
    city_id: int,
    meeting_date: dt.date,
    title: str,
    video_source: str,
    meeting_type: str | None = None,
) -> Meeting:
    city = session.get(City, city_id)
    if city is None:
        raise ValueError(f"No city with id={city_id}")

    meeting = Meeting(
        city_id=city_id,
        meeting_date=meeting_date,
        title=title,
        meeting_type=meeting_type,
        source_video_url=video_source if video_source.startswith("http") else None,
        status=TranscriptStatus.PENDING,
    )
    session.add(meeting)
    session.flush()  # assign meeting.id

    slug = f"{city.name.lower().replace(' ', '_')}_{meeting_date.isoformat()}_{meeting.id}"

    try:
        meeting.status = TranscriptStatus.TRANSCRIBING
        video_path = resolve_video(video_source, slug)
        meeting.source_video_path = str(video_path)

        audio_path = extract_audio(video_path, TRANSCRIPTS_DIR / f"{slug}.wav")
        segments = transcribe_audio(audio_path)
        diarization = diarize_audio(audio_path)
        turns = merge_transcript_and_diarization(segments, diarization)

        speaker_cache: dict[str, Speaker] = {}
        for i, turn in enumerate(turns):
            speaker = speaker_cache.get(turn.speaker_label)
            if speaker is None:
                suggested = suggest_speaker_name(turn.text)
                speaker = Speaker(
                    city_id=city_id,
                    name=None,
                    speaker_type=SpeakerType.UNKNOWN,
                    notes=(
                        f"Auto-detected as '{turn.speaker_label}' for meeting {meeting.id}."
                        + (f" Possible self-introduction: '{suggested}' — confirm before assigning."
                           if suggested else "")
                    ),
                )
                session.add(speaker)
                session.flush()
                speaker_cache[turn.speaker_label] = speaker

            session.add(
                Statement(
                    meeting_id=meeting.id,
                    speaker_id=speaker.id,
                    sequence=i,
                    start_seconds=turn.start,
                    end_seconds=turn.end,
                    text=turn.text,
                )
            )

        meeting.status = TranscriptStatus.TRANSCRIBED
    except Exception:
        meeting.status = TranscriptStatus.FAILED
        log.exception("Ingestion failed for meeting %s", meeting.id)
        raise

    session.flush()
    return meeting


def ingest_transcript_text(
    session: Session,
    city_id: int,
    meeting_date: dt.date,
    title: str,
    transcript_text: str,
    meeting_type: str | None = None,
) -> Meeting:
    """Text transcript, one paragraph per line (see ingest_transcript_lines for format)."""
    return ingest_transcript_lines(
        session, city_id, meeting_date, title, transcript_text.splitlines(), meeting_type=meeting_type
    )


def ingest_transcript_docx(
    session: Session,
    city_id: int,
    meeting_date: dt.date,
    title: str,
    docx_path: Path,
    meeting_type: str | None = None,
) -> Meeting:
    """Text transcript exported as a .docx (each paragraph a speaker turn)."""
    return ingest_transcript_lines(
        session, city_id, meeting_date, title, extract_docx_paragraphs(docx_path), meeting_type=meeting_type
    )


# Matches "Speaker Name: text" or "Speaker Name (Affiliation): text" at the start of a line.
_SPEAKER_LINE_RE = re.compile(r"^\s*([A-Z][A-Za-z .'()\-]{1,80}):\s*(.+)$")
# Inline minute-marker timestamps some transcription tools drop mid-sentence, e.g. "[00:12:34]".
_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2}):(\d{2})\]")
_AFFILIATION_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<affiliation>[^)]+)\)\s*$")

_OFFICIAL_TITLE_RE = re.compile(r"^(Council\s?Member|Councilmember|Chair|Vice Chair|Mayor|President)\b", re.I)
_STAFF_NAME_RE = re.compile(r"(City Clerk|City Administrator|Administration Staff|Mayor'?s Office Staff|Parliamentarian|\bStaff$)", re.I)


def _strip_timestamps(text: str) -> tuple[str, float | None]:
    """Remove inline [HH:MM:SS] markers, returning the cleaned text and the first timestamp (in seconds) if any."""
    matches = list(_TIMESTAMP_RE.finditer(text))
    first_seconds = None
    if matches:
        h, m, s = matches[0].groups()
        first_seconds = int(h) * 3600 + int(m) * 60 + int(s)
    cleaned = _TIMESTAMP_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, first_seconds


def _classify_speaker_type(label: str) -> SpeakerType:
    if _OFFICIAL_TITLE_RE.search(label):
        return SpeakerType.OFFICIAL
    if _STAFF_NAME_RE.search(label):
        return SpeakerType.STAFF
    return SpeakerType.PUBLIC


def _find_matching_official(session: Session, city_id: int, label: str) -> Official | None:
    """Best-effort match of a title-prefixed label (e.g. 'Council Member Houston') to a
    known Official by surname. Only links on an unambiguous single match — never guesses."""
    remainder = _OFFICIAL_TITLE_RE.sub("", label).strip()
    if not remainder:
        return None
    candidates = session.query(Official).filter(Official.city_id == city_id, Official.name.ilike(f"%{remainder}%")).all()
    return candidates[0] if len(candidates) == 1 else None


def _get_or_create_speaker(
    session: Session, city_id: int, cache: dict[str, Speaker], label: str
) -> Speaker:
    m = _AFFILIATION_RE.match(label)
    name, affiliation = (m.group("name"), m.group("affiliation")) if m else (label, None)

    cached = cache.get(name)
    if cached is not None:
        return cached

    speaker = session.query(Speaker).filter_by(city_id=city_id, name=name).one_or_none()
    if speaker is None:
        speaker_type = _classify_speaker_type(name)
        official = _find_matching_official(session, city_id, name) if speaker_type == SpeakerType.OFFICIAL else None
        speaker = Speaker(
            city_id=city_id,
            name=official.name if official else name,
            speaker_type=speaker_type,
            official_id=official.id if official else None,
            notes=f"Affiliation (from transcript): {affiliation}" if affiliation else None,
        )
        session.add(speaker)
        session.flush()
    cache[name] = speaker
    return speaker


def ingest_transcript_lines(
    session: Session,
    city_id: int,
    meeting_date: dt.date,
    title: str,
    lines: list[str],
    meeting_type: str | None = None,
) -> Meeting:
    """
    Core transcript ingestion. Each line is expected to start a new speaker turn in the
    form "Speaker Name: text" or "Speaker Name (Affiliation): text" — this is the format
    produced by exporting a diarized audio transcript to text/.docx. A line with no
    speaker prefix is treated as a continuation of the previous turn (common when a
    transcription tool splits one utterance across paragraphs); a line with no speaker
    prefix and no prior turn yet (e.g. a document header/ID some export tools add) is
    dropped. Inline "[HH:MM:SS]" markers are stripped from the text; the first one in a
    turn is kept as that statement's start_seconds.

    Speaker type (official/staff/public) is inferred from the label itself (e.g. "Council
    Member X", "City Clerk") — a factual read of the transcript's own labels, not a
    judgment about the person. An official label is linked to an existing Official row
    only on an unambiguous surname match; otherwise it's left unlinked for manual review.
    """
    city = session.get(City, city_id)
    if city is None:
        raise ValueError(f"No city with id={city_id}")

    meeting = Meeting(
        city_id=city_id,
        meeting_date=meeting_date,
        title=title,
        meeting_type=meeting_type,
        status=TranscriptStatus.TRANSCRIBED,
    )
    session.add(meeting)
    session.flush()

    speaker_cache: dict[str, Speaker] = {}
    current_speaker: Speaker | None = None
    current_statement: Statement | None = None
    seq = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        m = _SPEAKER_LINE_RE.match(line)
        if m:
            label, raw_text = m.group(1).strip(), m.group(2).strip()
            text, start_seconds = _strip_timestamps(raw_text)
            if not text:
                continue
            current_speaker = _get_or_create_speaker(session, city_id, speaker_cache, label)
            current_statement = Statement(
                meeting_id=meeting.id,
                speaker_id=current_speaker.id,
                sequence=seq,
                start_seconds=start_seconds,
                text=text,
            )
            session.add(current_statement)
            seq += 1
        elif current_statement is not None:
            # Continuation of the previous speaker's turn.
            text, _ = _strip_timestamps(line)
            if text:
                current_statement.text = f"{current_statement.text} {text}".strip()
        # else: no speaker seen yet — drop (e.g. a document header line some exports add).

    session.flush()
    return meeting
