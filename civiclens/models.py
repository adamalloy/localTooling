"""
ORM schema.

Deliberate scope boundary (see README "Scope decisions"): Official carries a full
public-accountability profile because council members and the politicians tracked
here (e.g. a supported candidate and her opposition) are public figures. Speaker
records for members of the public carry only evidence — what they said, on what
topic, when, how often — never a psychological/behavioral label ("aggressive",
"mainstream" vs "kooky") and never an automated ally/opponent flag. Anyone using
this tool decides who's an ally by reading the evidence themselves.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now() -> dt.datetime:
    return dt.datetime.utcnow()


class SpeakerType(str, enum.Enum):
    OFFICIAL = "official"
    STAFF = "staff"
    PUBLIC = "public"
    UNKNOWN = "unknown"


class Stance(str, enum.Enum):
    SUPPORT = "support"
    OPPOSE = "oppose"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class VoteValue(str, enum.Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    RECUSE = "recuse"
    ABSENT = "absent"


class DocumentType(str, enum.Enum):
    BUDGET = "budget"
    REPORT = "report"
    POLICY = "policy"
    MINUTES = "minutes"
    AGENDA = "agenda"
    OTHER = "other"


class TranscriptStatus(str, enum.Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    ANALYZED = "analyzed"
    FAILED = "failed"


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    state: Mapped[str] = mapped_column(String(2), default="CA")
    legistar_client: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    officials: Mapped[list["Official"]] = relationship(back_populates="city")
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="city")
    speakers: Mapped[list["Speaker"]] = relationship(back_populates="city")
    documents: Mapped[list["Document"]] = relationship(back_populates="city")


class Official(Base):
    """A public official. Full accountability profile — public figures, not private citizens."""

    __tablename__ = "officials"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "Councilmember, District 3"
    district: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Tags for the two politicians this tool is explicitly tracking positions relative to.
    is_reference_politician: Mapped[bool] = mapped_column(Boolean, default=False)  # e.g. Jamie Joyce
    is_reference_opposition: Mapped[bool] = mapped_column(Boolean, default=False)  # e.g. Lateefah Simon

    city: Mapped["City"] = relationship(back_populates="officials")
    platform_issues: Mapped[list["PlatformIssue"]] = relationship(back_populates="official")
    votes: Mapped[list["Vote"]] = relationship(back_populates="official")
    alignments: Mapped[list["OfficialAlignment"]] = relationship(back_populates="official")
    follow_ups: Mapped[list["FollowUpRecommendation"]] = relationship(back_populates="official")


class PlatformIssue(Base):
    """A stated position for a reference politician (e.g. what Jamie Joyce cares about)."""

    __tablename__ = "platform_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(ForeignKey("officials.id"))
    topic: Mapped[str] = mapped_column(String(200))
    position_summary: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 (low) - 5 (high)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    official: Mapped["Official"] = relationship(back_populates="platform_issues")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    meeting_date: Mapped[dt.date] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(300))
    meeting_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    legistar_event_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[TranscriptStatus] = mapped_column(
        Enum(TranscriptStatus), default=TranscriptStatus.PENDING
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    city: Mapped["City"] = relationship(back_populates="meetings")
    agenda_items: Mapped[list["AgendaItem"]] = relationship(back_populates="meeting")
    statements: Mapped[list["Statement"]] = relationship(back_populates="meeting")
    votes: Mapped[list["Vote"]] = relationship(back_populates="meeting")
    summary: Mapped["MeetingSummary | None"] = relationship(back_populates="meeting", uselist=False)


class AgendaItem(Base):
    __tablename__ = "agenda_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    item_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="agenda_items")
    statements: Mapped[list["Statement"]] = relationship(back_populates="agenda_item")
    votes: Mapped[list["Vote"]] = relationship(back_populates="agenda_item")


class Speaker(Base):
    """
    Anyone who spoke at a meeting. For SpeakerType.PUBLIC this is intentionally a thin
    identity record — name (once known) + type. Aggregate behavior (topics, attendance,
    grievances raised) is derived at query time from Statement rows, not stored as a
    label on the person. See module docstring.
    """

    __tablename__ = "speakers"
    __table_args__ = (UniqueConstraint("city_id", "name", name="uq_speaker_city_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # null until identified
    speaker_type: Mapped[SpeakerType] = mapped_column(Enum(SpeakerType), default=SpeakerType.UNKNOWN)
    official_id: Mapped[int | None] = mapped_column(ForeignKey("officials.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    city: Mapped["City"] = relationship(back_populates="speakers")
    official: Mapped["Official | None"] = relationship()
    statements: Mapped[list["Statement"]] = relationship(back_populates="speaker")


class Statement(Base):
    """One contiguous turn of speech by one speaker within a meeting."""

    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    agenda_item_id: Mapped[int | None] = mapped_column(ForeignKey("agenda_items.id"), nullable=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speakers.id"))
    sequence: Mapped[int] = mapped_column(Integer)  # order within the meeting
    start_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text)

    # Factual, content-derived flags — never a psychological verdict on the speaker.
    contains_grievance: Mapped[bool] = mapped_column(Boolean, default=False)
    grievance_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="statements")
    agenda_item: Mapped["AgendaItem | None"] = relationship(back_populates="statements")
    speaker: Mapped["Speaker"] = relationship(back_populates="statements")
    topics: Mapped[list["StatementTopic"]] = relationship(back_populates="statement")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)

    statement_links: Mapped[list["StatementTopic"]] = relationship(back_populates="topic")


class StatementTopic(Base):
    """Content-based topic + stance extracted from a single statement, with the source quote."""

    __tablename__ = "statement_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    stance: Mapped[Stance] = mapped_column(Enum(Stance), default=Stance.NEUTRAL)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    statement: Mapped["Statement"] = relationship(back_populates="topics")
    topic: Mapped["Topic"] = relationship(back_populates="statement_links")


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(ForeignKey("officials.id"))
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    agenda_item_id: Mapped[int | None] = mapped_column(ForeignKey("agenda_items.id"), nullable=True)
    vote_value: Mapped[VoteValue] = mapped_column(Enum(VoteValue))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    official: Mapped["Official"] = relationship(back_populates="votes")
    meeting: Mapped["Meeting"] = relationship(back_populates="votes")
    agenda_item: Mapped["AgendaItem | None"] = relationship(back_populates="votes")


class Document(Base):
    """Budgets, reports, policies, minutes, agendas — ingested from the city's own sources."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id"), nullable=True)
    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    title: Mapped[str] = mapped_column(String(400))
    source_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(700), nullable=True)
    published_date: Mapped[dt.date | None] = mapped_column(DateTime, nullable=True)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    city: Mapped["City"] = relationship(back_populates="documents")


class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), primary_key=True)
    summary_text: Mapped[str] = mapped_column(Text)
    key_takeaways: Mapped[list] = mapped_column(JSON, default=list)
    controversial_topics: Mapped[list] = mapped_column(JSON, default=list)  # [{topic, split, notes}]
    consensus_topics: Mapped[list] = mapped_column(JSON, default=list)  # [{topic, notes}]
    public_speaker_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    meeting: Mapped["Meeting"] = relationship(back_populates="summary")


class OfficialAlignment(Base):
    """How aligned an official's votes/statements are with a reference platform issue."""

    __tablename__ = "official_alignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(ForeignKey("officials.id"))
    platform_issue_id: Mapped[int] = mapped_column(ForeignKey("platform_issues.id"))
    alignment_score: Mapped[float] = mapped_column(Float)  # -1 (opposed) .. 1 (aligned)
    rationale: Mapped[str] = mapped_column(Text)
    evidence_statement_ids: Mapped[list] = mapped_column(JSON, default=list)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    official: Mapped["Official"] = relationship(back_populates="alignments")
    platform_issue: Mapped["PlatformIssue"] = relationship()


class FollowUpRecommendation(Base):
    """Suggested outreach toward a council member — never generated for private speakers."""

    __tablename__ = "follow_up_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    official_id: Mapped[int] = mapped_column(ForeignKey("officials.id"))
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/done/dismissed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    official: Mapped["Official"] = relationship(back_populates="follow_ups")
    meeting: Mapped["Meeting | None"] = relationship()
