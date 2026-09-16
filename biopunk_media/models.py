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
