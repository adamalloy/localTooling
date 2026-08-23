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
from civiclens.ingestion.video_source import resolve_video
from civiclens.models import City, Meeting, Speaker, SpeakerType, Statement, TranscriptStatus

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
    """
    For meetings where you already have an official transcript (e.g. clerk-published
    minutes with speaker labels) instead of raw video. Expects lines roughly in the
    form "SPEAKER NAME: text" — unlabeled lines are attributed to a single Unknown
    Speaker for manual cleanup in the UI.
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

    line_re = re.compile(r"^\s*([A-Z][A-Za-z .'\-]{1,60}):\s*(.+)$")
    speaker_cache: dict[str, Speaker] = {}
    seq = 0
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = line_re.match(line)
        name, text = (m.group(1).strip(), m.group(2).strip()) if m else (None, line)

        key = name or "__unknown__"
        speaker = speaker_cache.get(key)
        if speaker is None:
            speaker = (
                session.query(Speaker).filter_by(city_id=city_id, name=name).one_or_none()
                if name
                else None
            )
            if speaker is None:
                speaker = Speaker(
                    city_id=city_id,
                    name=name,
                    speaker_type=SpeakerType.UNKNOWN if name else SpeakerType.UNKNOWN,
                )
                session.add(speaker)
                session.flush()
            speaker_cache[key] = speaker

        session.add(Statement(meeting_id=meeting.id, speaker_id=speaker.id, sequence=seq, text=text))
        seq += 1

    session.flush()
    return meeting
