"""
Seed starter data for Biopunk Media.

Houses are seeded from what's publicly documented about the Biopunk
residency network (PunkHaus, FemHaus, SafeHaus, AlumHaus, and the Kobe
cell & gene therapy house) — see the project README for sources.

Companies, members, and content items below are clearly-labeled EXAMPLE rows,
not a verified roster: current cohort membership wasn't confirmed from public
sources. Delete/replace them with the real roster before using this for
anything but a demo of the tool.

Usage:
    python scripts/seed_biopunk_ecosystem.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biopunk_media.db import init_db, session_scope
from biopunk_media.models import (
    Company,
    CompanyStage,
    ContentItem,
    ContentItemPlatform,
    ContentStatus,
    ContentType,
    House,
    HouseKind,
    Member,
    Platform,
    ScopeType,
    SocialAccount,
)


def slugify(name: str) -> str:
    return name.lower().replace(" ", "-").replace("'", "")


HOUSES = [
    dict(
        name="PunkHaus",
        kind=HouseKind.FLAGSHIP,
        city="San Francisco",
        description="The fundraising flagship: cohort housing, dry-lab workspace, weekly "
        "dinners — where companies go from angel to seed.",
    ),
    dict(
        name="FemHaus",
        kind=HouseKind.FEMHAUS,
        city="San Francisco",
        description="An all-women founder residence.",
    ),
    dict(
        name="SafeHaus",
        kind=HouseKind.SAFEHAUS,
        city="San Francisco",
        description="A biosecurity house: countermeasures, DNA-synthesis screening, "
        "and biosurveillance.",
    ),
    dict(
        name="AlumHaus",
        kind=HouseKind.ALUMHAUS,
        city="San Francisco",
        description="The alumni house — graduated founders keep building in the network.",
    ),
    dict(
        name="Kobe Cell & Gene Therapy House",
        kind=HouseKind.SATELLITE,
        city="Kobe, Japan",
        description="A cell & gene therapy house inside the Kobe Biomedical Innovation "
        "Cluster.",
    ),
]

# EXAMPLE data only — replace with the real current roster.
EXAMPLE_COMPANIES = [
    dict(name="Example Biotech Co", house="PunkHaus", stage=CompanyStage.COHORT,
         cohort="Example cohort", one_liner="Placeholder — replace with a real cohort company."),
]

EXAMPLE_MEMBERS = [
    dict(name="Jordan Example", role="Co-founder / CEO", company="Example Biotech Co", house="PunkHaus"),
    dict(name="Sam Example", role="Co-founder / CSO", company="Example Biotech Co", house="PunkHaus"),
]


def run() -> None:
    init_db()
    with session_scope() as session:
        house_rows: dict[str, House] = {}
        for h in HOUSES:
            existing = session.query(House).filter_by(slug=slugify(h["name"])).one_or_none()
            if existing:
                house_rows[h["name"]] = existing
                continue
            house = House(
                name=h["name"],
                slug=slugify(h["name"]),
                kind=h["kind"],
                city=h["city"],
                description=h["description"],
            )
            session.add(house)
            session.flush()
            house_rows[h["name"]] = house

        company_rows: dict[str, Company] = {}
        for c in EXAMPLE_COMPANIES:
            existing = session.query(Company).filter_by(slug=slugify(c["name"])).one_or_none()
            if existing:
                company_rows[c["name"]] = existing
                continue
            company = Company(
                name=c["name"],
                slug=slugify(c["name"]),
                house_id=house_rows[c["house"]].id if c.get("house") else None,
                stage=c["stage"],
                cohort=c.get("cohort"),
                one_liner=c.get("one_liner"),
            )
            session.add(company)
            session.flush()
            company_rows[c["name"]] = company

        member_rows: dict[str, Member] = {}
        for m in EXAMPLE_MEMBERS:
            existing = session.query(Member).filter_by(slug=slugify(m["name"])).one_or_none()
            if existing:
                member_rows[m["name"]] = existing
                continue
            member = Member(
                name=m["name"],
                slug=slugify(m["name"]),
                role=m.get("role"),
                company_id=company_rows[m["company"]].id if m.get("company") else None,
                house_id=house_rows[m["house"]].id if m.get("house") else None,
            )
            session.add(member)
            session.flush()
            member_rows[m["name"]] = member

        if not session.query(SocialAccount).filter_by(owner_type=ScopeType.PROJECT).count():
            session.add(
                SocialAccount(
                    owner_type=ScopeType.PROJECT,
                    owner_id=None,
                    platform=Platform.INSTAGRAM,
                    handle="@biopunklabs",
                )
            )

        if not session.query(ContentItem).count():
            example = ContentItem(
                title="Example: cohort welcome video",
                summary="Placeholder content item so the calendar isn't empty on first run.",
                content_type=ContentType.VIDEO,
                scope_type=ScopeType.PROJECT,
                scope_id=None,
                status=ContentStatus.IDEA,
                scheduled_at=dt.datetime.utcnow() + dt.timedelta(days=3),
            )
            session.add(example)
            session.flush()
            session.add(ContentItemPlatform(content_item_id=example.id, platform=Platform.YOUTUBE))

    print("Seeded houses:", ", ".join(house_rows))
    print("Seeded example companies/members/content — replace before real use.")


if __name__ == "__main__":
    run()
