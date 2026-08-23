"""Pydantic schemas used as structured-output targets for LLM extraction calls."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TopicStance(BaseModel):
    topic: str = Field(description="Short topic/issue name, e.g. 'Encampment sweeps', 'Police budget'")
    stance: str = Field(description="One of: support, oppose, neutral, mixed")
    evidence_quote: str = Field(description="A short direct quote from the statement supporting this stance")
    confidence: float = Field(description="0.0-1.0 confidence in this topic/stance extraction")


class GrievanceFlag(BaseModel):
    contains_grievance: bool = Field(
        description="True if the speaker describes being mistreated, harmed, or wronged by the "
        "city, a department, or the council"
    )
    grievance_summary: str | None = Field(
        default=None, description="One-sentence factual summary of the grievance, or null"
    )


class StatementAnalysis(BaseModel):
    topics: list[TopicStance] = Field(default_factory=list)
    grievance: GrievanceFlag


class TopicSplit(BaseModel):
    topic: str
    notes: str = Field(description="What the disagreement or consensus is about")


class MeetingSummaryResult(BaseModel):
    summary_text: str = Field(description="3-6 sentence plain-language summary of the meeting")
    key_takeaways: list[str] = Field(default_factory=list)
    controversial_topics: list[TopicSplit] = Field(
        default_factory=list, description="Topics where speakers/officials clearly disagreed"
    )
    consensus_topics: list[TopicSplit] = Field(
        default_factory=list, description="Topics where speakers/officials were largely aligned"
    )


class AlignmentResult(BaseModel):
    alignment_score: float = Field(description="-1.0 (opposed) to 1.0 (aligned) with the platform issue")
    rationale: str = Field(description="1-3 sentences citing specific votes/statements")


class FollowUpSuggestion(BaseModel):
    reason: str
    suggested_action: str
    priority: int = Field(description="1 (low) to 5 (high)")
