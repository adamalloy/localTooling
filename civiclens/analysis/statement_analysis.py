"""
Per-statement content extraction: what topics were raised, what stance was taken,
and whether the speaker describes being mistreated by the city. Deliberately
content-only — no tone/psychological classification of the speaker. See
civiclens/models.py module docstring for the scope rationale.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from civiclens.analysis.llm import extract
from civiclens.models import Statement, StatementTopic, Stance, Topic
from civiclens.schemas import StatementAnalysis

SYSTEM_PROMPT = """You analyze a single spoken turn from a city council meeting transcript.
Extract only what is actually said. Do not infer the speaker's psychological state,
credibility, or political affiliation. For each distinct policy topic raised, name it
concisely, classify the stance taken (support/oppose/neutral/mixed) toward that topic,
and quote the exact phrase that supports your classification. Separately, flag only if
the speaker describes concrete mistreatment or harm caused by the city, a department,
or the council (e.g. wrongful citation, unresponsive agency, unsafe conditions ignored) —
not mere disagreement with a policy."""


def analyze_statement(session: Session, statement: Statement) -> StatementAnalysis:
    user = f"Transcript excerpt (single speaker turn):\n\n{statement.text}"
    result = extract(SYSTEM_PROMPT, user, StatementAnalysis)

    statement.contains_grievance = result.grievance.contains_grievance
    statement.grievance_summary = result.grievance.grievance_summary

    for t in result.topics:
        topic = session.query(Topic).filter_by(name=t.topic).one_or_none()
        if topic is None:
            topic = Topic(name=t.topic)
            session.add(topic)
            session.flush()
        try:
            stance = Stance(t.stance.lower().strip())
        except ValueError:
            stance = Stance.NEUTRAL
        session.add(
            StatementTopic(
                statement_id=statement.id,
                topic_id=topic.id,
                stance=stance,
                confidence=t.confidence,
                evidence_quote=t.evidence_quote,
            )
        )

    return result


def analyze_meeting_statements(session: Session, meeting_id: int) -> int:
    statements = session.query(Statement).filter_by(meeting_id=meeting_id).order_by(Statement.sequence).all()
    for s in statements:
        analyze_statement(session, s)
    session.flush()
    return len(statements)
