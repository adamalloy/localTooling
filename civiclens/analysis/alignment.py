"""
Score how aligned an official's public record is with a reference politician's
platform (e.g. Jamie Joyce's stated positions), and generate follow-up
recommendations for engaging that official. Applies to Official rows only —
public officials are the accountability subject here, never private speakers.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from civiclens.analysis.llm import extract
from civiclens.models import (
    FollowUpRecommendation,
    Official,
    OfficialAlignment,
    PlatformIssue,
    Statement,
    StatementTopic,
    Topic,
    Vote,
)
from civiclens.schemas import AlignmentResult, FollowUpSuggestion

ALIGNMENT_SYSTEM_PROMPT = """You compare a city council member's public record (votes and
statements) against a single stated policy position of another politician. Score how
aligned the council member's actual record is with that position, from -1.0 (directly
opposed) to 1.0 (fully aligned), and cite specific evidence. If there is no relevant
record, score 0.0 and say so."""

FOLLOWUP_SYSTEM_PROMPT = """You advise a political organizer on how to follow up with a
city council member, given their alignment (or misalignment) with a specific policy
position. Suggest one concrete, low-key, appropriate next step (e.g. "thank them for
their vote on X and ask about timeline for Y", "request a meeting to discuss Z before
the next budget cycle"). Do not suggest anything pressuring, deceptive, or that
misrepresents who the organizer is."""


def _official_record_text(session: Session, official: Official, topic_name: str) -> str:
    votes = session.query(Vote).filter_by(official_id=official.id).all()
    vote_lines = [f"- Vote on agenda item {v.agenda_item_id}: {v.vote_value.value}" for v in votes]

    statements = (
        session.query(Statement)
        .join(StatementTopic)
        .join(Topic)
        .filter(Statement.speaker.has(official_id=official.id), Topic.name.ilike(f"%{topic_name}%"))
        .all()
    )
    stmt_lines = [f"- \"{s.text[:400]}\"" for s in statements]

    return "Votes:\n" + ("\n".join(vote_lines) or "(none recorded)") + \
        "\n\nRelevant statements:\n" + ("\n".join(stmt_lines) or "(none found)")


def score_alignment(session: Session, official_id: int, platform_issue_id: int) -> OfficialAlignment:
    official = session.get(Official, official_id)
    issue = session.get(PlatformIssue, platform_issue_id)
    if official is None or issue is None:
        raise ValueError("Official or PlatformIssue not found")

    record = _official_record_text(session, official, issue.topic)
    user = (
        f"Reference position ({issue.topic}): {issue.position_summary}\n\n"
        f"{official.name}'s record:\n{record}"
    )
    result: AlignmentResult = extract(ALIGNMENT_SYSTEM_PROMPT, user, AlignmentResult, max_tokens=1024)

    alignment = (
        session.query(OfficialAlignment)
        .filter_by(official_id=official_id, platform_issue_id=platform_issue_id)
        .one_or_none()
    )
    if alignment is None:
        alignment = OfficialAlignment(official_id=official_id, platform_issue_id=platform_issue_id)
        session.add(alignment)

    alignment.alignment_score = result.alignment_score
    alignment.rationale = result.rationale
    session.flush()
    return alignment


def generate_follow_up(
    session: Session, official_id: int, platform_issue_id: int, meeting_id: int | None = None
) -> FollowUpRecommendation:
    official = session.get(Official, official_id)
    issue = session.get(PlatformIssue, platform_issue_id)
    alignment = (
        session.query(OfficialAlignment)
        .filter_by(official_id=official_id, platform_issue_id=platform_issue_id)
        .one_or_none()
    )
    if official is None or issue is None:
        raise ValueError("Official or PlatformIssue not found")

    score_desc = f"{alignment.alignment_score:+.2f}" if alignment else "not yet scored"
    user = (
        f"Council member: {official.name} ({official.role})\n"
        f"Policy position: {issue.topic} — {issue.position_summary}\n"
        f"Current alignment score: {score_desc}\n"
        f"Rationale: {alignment.rationale if alignment else 'n/a'}"
    )
    result: FollowUpSuggestion = extract(FOLLOWUP_SYSTEM_PROMPT, user, FollowUpSuggestion, max_tokens=512)

    rec = FollowUpRecommendation(
        official_id=official_id,
        meeting_id=meeting_id,
        reason=result.reason,
        suggested_action=result.suggested_action,
        priority=result.priority,
    )
    session.add(rec)
    session.flush()
    return rec
