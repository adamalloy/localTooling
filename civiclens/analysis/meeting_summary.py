"""Whole-meeting summary, key takeaways, and controversy-vs-consensus detection."""
from __future__ import annotations

from sqlalchemy.orm import Session

from civiclens.analysis.llm import extract
from civiclens.models import Meeting, MeetingSummary, Speaker, SpeakerType, Statement, TranscriptStatus
from civiclens.schemas import MeetingSummaryResult

SYSTEM_PROMPT = """You summarize a city council meeting from its full transcript.
Write a plain-language summary a busy constituent could read in 30 seconds, then list
3-8 key takeaways. Identify topics where speakers or officials clearly disagreed
(controversial) and topics where there was broad agreement (consensus). Base every
claim on what is actually in the transcript."""

# Transcripts can be long; give the model plenty of room but keep a sane ceiling
# per call — very long meetings should be chunked by the caller if needed.
MAX_TRANSCRIPT_CHARS = 180_000


def _build_transcript_text(session: Session, meeting_id: int) -> str:
    statements = (
        session.query(Statement)
        .filter_by(meeting_id=meeting_id)
        .order_by(Statement.sequence)
        .all()
    )
    lines = []
    for s in statements:
        label = s.speaker.name or f"Speaker {s.speaker_id}"
        lines.append(f"{label}: {s.text}")
    text = "\n".join(lines)
    return text[:MAX_TRANSCRIPT_CHARS]


def summarize_meeting(session: Session, meeting_id: int) -> MeetingSummary:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise ValueError(f"No meeting with id={meeting_id}")

    transcript_text = _build_transcript_text(session, meeting_id)
    user = f"Meeting: {meeting.title} ({meeting.meeting_date})\n\nTranscript:\n\n{transcript_text}"
    result: MeetingSummaryResult = extract(SYSTEM_PROMPT, user, MeetingSummaryResult, max_tokens=8192)

    public_speaker_ids = (
        session.query(Statement.speaker_id)
        .join(Speaker)
        .filter(Statement.meeting_id == meeting_id, Speaker.speaker_type == SpeakerType.PUBLIC)
        .distinct()
        .count()
    )

    summary = session.get(MeetingSummary, meeting_id)
    if summary is None:
        summary = MeetingSummary(meeting_id=meeting_id)
        session.add(summary)

    summary.summary_text = result.summary_text
    summary.key_takeaways = result.key_takeaways
    summary.controversial_topics = [t.model_dump() for t in result.controversial_topics]
    summary.consensus_topics = [t.model_dump() for t in result.consensus_topics]
    summary.public_speaker_count = public_speaker_ids

    meeting.status = TranscriptStatus.ANALYZED
    session.flush()
    return summary
