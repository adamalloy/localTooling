"""
Topic/stance/grievance extraction across a whole meeting.

This makes one LLM call for a meeting that fits in a single context window, and only
splits into a handful of chunked calls for an unusually long one — never one call per
statement. Statements are referenced by their real database id, embedded in the prompt
as "[#123]", so results map straight back onto specific Statement rows with no fuzzy
text matching.

Content-only extraction — see civiclens/models.py module docstring for the scope
rationale (no psychological/behavioral judgment of speakers).
"""
from __future__ import annotations

import logging

import pydantic
from sqlalchemy.orm import Session

from civiclens.analysis.llm import extract
from civiclens.models import Stance, Statement, StatementTopic, Topic
from civiclens.schemas import TopicsAndGrievances

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You analyze a full city council meeting transcript. Each line is one
speaker's turn, prefixed with its database id like "[#123] Speaker: text" — always cite
that exact id back as statement_index, never a line number or a guess.

For every distinct policy topic raised anywhere in the transcript, record each mention:
which statement raised it, the stance taken (support/oppose/neutral/mixed), and a short
exact quote supporting that classification. A single statement can raise multiple
topics. Do not infer the speaker's psychological state, credibility, or political
affiliation — classify only the content of what they said.

Separately, flag only statements where the speaker describes concrete mistreatment or
harm caused by the city, a department, or the council (e.g. wrongful citation,
unresponsive agency, unsafe conditions ignored) — not mere disagreement with a policy."""

# One call per chunk this size. Bounded well under the model's context window — the
# limit that actually matters here is the *output* budget (EXTRACT_MAX_TOKENS below):
# a chunk this size raises enough topic mentions to comfortably fit that budget for a
# typical meeting, while still cutting a few-hundred-statement meeting down to a
# handful of calls instead of one per statement.
MAX_CHUNK_CHARS = 45_000
EXTRACT_MAX_TOKENS = 16_000
MIN_CHUNK_STATEMENTS = 3  # below this, a failure is logged and skipped rather than split further


def _chunk_statements(statements: list[Statement], max_chars: int) -> list[list[Statement]]:
    chunks: list[list[Statement]] = []
    current: list[Statement] = []
    current_len = 0
    for s in statements:
        line_len = len(s.text) + 50  # rough allowance for the "[#id] Speaker: " prefix
        if current and current_len + line_len > max_chars:
            chunks.append(current)
            current, current_len = [], 0
        current.append(s)
        current_len += line_len
    if current:
        chunks.append(current)
    return chunks


def _render(statements: list[Statement]) -> str:
    lines = []
    for s in statements:
        label = s.speaker.name or f"Speaker {s.speaker_id}"
        lines.append(f"[#{s.id}] {label}: {s.text}")
    return "\n".join(lines)


def _apply_result(session: Session, result: TopicsAndGrievances, by_id: dict[int, Statement]) -> None:
    for mention in result.topic_mentions:
        statement = by_id.get(mention.statement_index)
        if statement is None:
            continue  # model cited an id we didn't send it — skip rather than guess
        topic = session.query(Topic).filter_by(name=mention.topic).one_or_none()
        if topic is None:
            topic = Topic(name=mention.topic)
            session.add(topic)
            session.flush()
        try:
            stance = Stance(mention.stance.lower().strip())
        except ValueError:
            stance = Stance.NEUTRAL
        session.add(
            StatementTopic(
                statement_id=statement.id,
                topic_id=topic.id,
                stance=stance,
                confidence=mention.confidence,
                evidence_quote=mention.evidence_quote,
            )
        )

    for g in result.grievances:
        statement = by_id.get(g.statement_index)
        if statement is None:
            continue
        statement.contains_grievance = True
        statement.grievance_summary = g.summary


def _process_chunk(session: Session, chunk: list[Statement], by_id: dict[int, Statement]) -> None:
    """
    Extracts one chunk. If the model's output gets cut off — most likely when a chunk
    raises more topics than fit in EXTRACT_MAX_TOKENS — parsing the (truncated) JSON
    raises a pydantic ValidationError; rather than losing the whole meeting's analysis
    to that, split the chunk in half and retry each half, down to MIN_CHUNK_STATEMENTS,
    where a further failure is logged and that handful of statements is skipped.

    Deliberately only catches ValidationError, the specific symptom of truncated
    output — anything else (auth failure, rate limit, network error, ...) propagates
    immediately instead of being silently retried into oblivion and hidden.
    """
    try:
        result: TopicsAndGrievances = extract(
            SYSTEM_PROMPT, _render(chunk), TopicsAndGrievances, max_tokens=EXTRACT_MAX_TOKENS
        )
    except pydantic.ValidationError:
        if len(chunk) <= MIN_CHUNK_STATEMENTS:
            log.warning(
                "Topic extraction failed for statement ids %s after splitting down to %d "
                "statement(s); skipping.",
                [s.id for s in chunk],
                len(chunk),
                exc_info=True,
            )
            return
        mid = len(chunk) // 2
        _process_chunk(session, chunk[:mid], by_id)
        _process_chunk(session, chunk[mid:], by_id)
        return

    _apply_result(session, result, by_id)


def analyze_meeting_topics(session: Session, meeting_id: int) -> int:
    """Populates StatementTopic rows and Statement grievance fields for a whole meeting.
    Returns the number of statements covered. Clears any previous results for this
    meeting first, so it's safe to re-run."""
    statements = (
        session.query(Statement).filter_by(meeting_id=meeting_id).order_by(Statement.sequence).all()
    )
    if not statements:
        return 0

    statement_ids = [s.id for s in statements]
    session.query(StatementTopic).filter(StatementTopic.statement_id.in_(statement_ids)).delete(
        synchronize_session=False
    )
    for s in statements:
        s.contains_grievance = False
        s.grievance_summary = None

    by_id = {s.id: s for s in statements}
    for chunk in _chunk_statements(statements, MAX_CHUNK_CHARS):
        _process_chunk(session, chunk, by_id)

    session.flush()
    return len(statements)
