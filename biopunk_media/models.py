"""
ORM schema for Biopunk Media.

Scope model: every piece of content belongs to exactly one of four scopes —
MEMBER, COMPANY, HOUSE, or PROJECT (ecosystem-wide, e.g. the Biopunk Community
map or a cross-house announcement). `ContentItem.scope_type` + `scope_id`
together point at the owning row (scope_id is null for PROJECT). It's a
lightweight polymorphic association rather than three separate nullable FKs,
because a content item has exactly one owner and the four scopes are mutually
exclusive — see `ContentItem.scope_label` / the web layer for how scope_id is
resolved back to a Member/Company/House.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now() -> dt.datetime:
    return dt.datetime.utcnow()


class HouseKind(str, enum.Enum):
    FLAGSHIP = "flagship"          # e.g. PunkHaus
    FEMHAUS = "femhaus"
    SAFEHAUS = "safehaus"
    ALUMHAUS = "alumhaus"
    SATELLITE = "satellite"        # e.g. the Kobe cell & gene therapy house
    OTHER = "other"


class CompanyStage(str, enum.Enum):
    PROSPECT = "prospect"
    COHORT = "cohort"
    ALUMNI = "alumni"
    NETWORK = "network"            # movement-wide member org, not an in-house cohort company


class Platform(str, enum.Enum):
    INSTAGRAM = "instagram"
    X = "x"
    LINKEDIN = "linkedin"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    NEWSLETTER = "newsletter"
    BLOG = "blog"
    PRESS = "press"
    OTHER = "other"


class ScopeType(str, enum.Enum):
    MEMBER = "member"
    COMPANY = "company"
    HOUSE = "house"
    PROJECT = "project"


class ContentType(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"
    ARTICLE = "article"
    SOCIAL_POST = "social_post"
    STORY = "story"
    NEWSLETTER = "newsletter"
    PRESS = "press"
    OTHER = "other"


class ContentStatus(str, enum.Enum):
    IDEA = "idea"
    DRAFTING = "drafting"
    IN_REVIEW = "in_review"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MediaSourceType(str, enum.Enum):
    UPLOAD = "upload"      # file stored locally under config.UPLOADS_DIR
    LINK = "link"           # external URL — nothing stored locally


class TranscriptSource(str, enum.Enum):
    NONE = "none"
    PROVIDED = "provided"    # pasted/uploaded by hand
    GENERATED = "generated"  # produced by scripts/transcribe_media.py (local Whisper)


class TranscriptStatus(str, enum.Enum):
    NONE = "none"
    PENDING = "pending"      # queued for scripts/transcribe_media.py
    READY = "ready"
    FAILED = "failed"


class SummaryStatus(str, enum.Enum):
    NONE = "none"
    READY = "ready"
    FAILED = "failed"


class IdeaStatus(str, enum.Enum):
    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    SHIPPED = "shipped"
    DECLINED = "declined"


class House(Base):
    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    kind: Mapped[HouseKind] = mapped_column(Enum(HouseKind), default=HouseKind.OTHER)
    city: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    companies: Mapped[list["Company"]] = relationship(back_populates="house")
    members: Mapped[list["Member"]] = relationship(back_populates="house")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id"))
    stage: Mapped[CompanyStage] = mapped_column(Enum(CompanyStage), default=CompanyStage.PROSPECT)
    cohort: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(500))
    one_liner: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    house: Mapped[House | None] = relationship(back_populates="companies")
    members: Mapped[list["Member"]] = relationship(back_populates="company")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    role: Mapped[str | None] = mapped_column(String(200))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id"))
    email: Mapped[str | None] = mapped_column(String(300))
    bio: Mapped[str | None] = mapped_column(Text)
    headshot_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    company: Mapped[Company | None] = relationship(back_populates="members")
    house: Mapped[House | None] = relationship(back_populates="members")


class SocialAccount(Base):
    """A platform handle owned by a member, company, house, or the project itself."""

    __tablename__ = "social_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_type: Mapped[ScopeType] = mapped_column(Enum(ScopeType), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer)  # null when owner_type == PROJECT
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500))


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), default=ContentType.OTHER)

    scope_type: Mapped[ScopeType] = mapped_column(Enum(ScopeType), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer)  # null when scope_type == PROJECT

    status: Mapped[ContentStatus] = mapped_column(Enum(ContentStatus), default=ContentStatus.IDEA)
    owner_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))

    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    asset_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    owner_member: Mapped[Member | None] = relationship()
    platforms: Mapped[list["ContentItemPlatform"]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan"
    )


class ContentItemPlatform(Base):
    """Which platform(s) a content item goes out on (many-to-many)."""

    __tablename__ = "content_item_platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)

    content_item: Mapped[ContentItem] = relationship(back_populates="platforms")


class MediaAsset(Base):
    """
    A source video (presentation, pitch, demo day talk, etc.) — the raw material
    the media engine works from, as distinct from `ContentItem` (a planned/published
    piece of outbound content). Scoped the same way as ContentItem: member / company /
    house / project.
    """

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    scope_type: Mapped[ScopeType] = mapped_column(Enum(ScopeType), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer)  # null when scope_type == PROJECT

    source_type: Mapped[MediaSourceType] = mapped_column(Enum(MediaSourceType), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500))  # relative to config.UPLOADS_DIR
    original_filename: Mapped[str | None] = mapped_column(String(300))
    external_url: Mapped[str | None] = mapped_column(String(500))

    transcript_text: Mapped[str | None] = mapped_column(Text)
    transcript_source: Mapped[TranscriptSource] = mapped_column(
        Enum(TranscriptSource), default=TranscriptSource.NONE
    )
    transcript_status: Mapped[TranscriptStatus] = mapped_column(
        Enum(TranscriptStatus), default=TranscriptStatus.NONE
    )

    summary: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[str | None] = mapped_column(Text)  # one bullet per line
    summary_status: Mapped[SummaryStatus] = mapped_column(Enum(SummaryStatus), default=SummaryStatus.NONE)
    summary_generated_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    ideas: Mapped[list["ProposedIdea"]] = relationship(
        back_populates="media_asset", cascade="all, delete-orphan"
    )


class ProposedIdea(Base):
    """
    An idea extracted from a video (by the AI summary pass, or added by hand),
    tracked as its own item with a status — separate from the freeform summary
    text so it doesn't disappear on re-summarize and can be followed up on.
    """

    __tablename__ = "proposed_ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IdeaStatus] = mapped_column(Enum(IdeaStatus), default=IdeaStatus.PROPOSED)
    source: Mapped[str] = mapped_column(String(20), default="ai")  # "ai" or "manual"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    media_asset: Mapped[MediaAsset] = relationship(back_populates="ideas")
