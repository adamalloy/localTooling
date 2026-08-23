#!/usr/bin/env python3
"""
Seed a reference politician (e.g. Jamie Joyce) and her platform issues, so
official alignment scoring and follow-up recommendations have something to
compare against.

Edit the PLATFORM list below, then run:
  python scripts/seed_platform.py --city Oakland --politician "Jamie Joyce" --role "Councilmember"
  python scripts/seed_platform.py --city Oakland --politician "Lateefah Simon" --role "Opposition" --opposition
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from civiclens.db import init_db, session_scope
from civiclens.models import City, Official, PlatformIssue

# Fill this in with the reference politician's actual stated positions before running
# with --politician set to her name. Each entry: (topic, position_summary, priority 1-5, source_url).
PLATFORM: list[tuple[str, str, int, str | None]] = [
    # ("Affordable housing", "Supports expanding inclusionary zoning requirements citywide.", 5, None),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", required=True)
    parser.add_argument("--politician", required=True)
    parser.add_argument("--role", default=None)
    parser.add_argument("--opposition", action="store_true", help="Mark this official as the tracked opposition")
    args = parser.parse_args()

    init_db()
    with session_scope() as db:
        city = db.query(City).filter_by(name=args.city).one_or_none()
        if city is None:
            city = City(name=args.city)
            db.add(city)
            db.flush()

        official = db.query(Official).filter_by(city_id=city.id, name=args.politician).one_or_none()
        if official is None:
            official = Official(city_id=city.id, name=args.politician, role=args.role)
            db.add(official)
            db.flush()

        official.is_reference_opposition = args.opposition
        official.is_reference_politician = not args.opposition

        if not args.opposition:
            if not PLATFORM:
                print("PLATFORM list is empty — edit scripts/seed_platform.py with her actual positions first.")
            for topic, summary, priority, source in PLATFORM:
                existing = db.query(PlatformIssue).filter_by(official_id=official.id, topic=topic).one_or_none()
                if existing is None:
                    db.add(PlatformIssue(official_id=official.id, topic=topic, position_summary=summary, priority=priority, source_url=source))

        print(f"Seeded {args.politician} (official id={official.id}, opposition={args.opposition}).")


if __name__ == "__main__":
    main()
