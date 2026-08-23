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

# Each entry: (topic, position_summary, priority 1-5, source_url).
#
# NOTE: the position_summary text below is a generic placeholder derived only from the
# topic name you gave me — I don't have Jamie Joyce's actual stated positions or quotes
# on these issues. Alignment scoring (civiclens/analysis/alignment.py) uses this text as
# the reference to compare council members' votes/statements against, so a vague or
# wrong summary produces a misleading score. Replace each summary with her real position
# (ideally a paraphrase close to her own words) and fill in source_url with a link to
# where she said it, before running alignment scoring for real.
PLATFORM: list[tuple[str, str, int, str | None]] = [
    ("AI Reform", "Supports regulating artificial intelligence development and deployment. TODO: replace with her specific stated position.", 3, None),
    ("Data Surveillance", "Opposes government/corporate data surveillance overreach and supports resident privacy protections. TODO: replace with her specific stated position.", 3, None),
    ("Sex Abuse and Trafficking", "Supports stronger action against sex abuse and human trafficking and support for survivors. TODO: replace with her specific stated position.", 3, None),
    ("ICE Reform", "Supports reforming ICE enforcement practices and protections for immigrant communities. TODO: replace with her specific stated position.", 3, None),
    ("Government Digitization", "Supports modernizing and digitizing government services and records. TODO: replace with her specific stated position.", 3, None),
    ("Epstein", "Supports transparency and accountability regarding the Jeffrey Epstein case and related institutional failures. TODO: replace with her specific stated position.", 3, None),
    ("Sugar", "Position on sugar-related policy (e.g. public health regulation). TODO: this topic is ambiguous from the name alone — clarify and replace with her specific stated position.", 3, None),
    ("Union and Labor Disputes", "Supports organized labor and fair resolution of union/labor disputes. TODO: replace with her specific stated position.", 3, None),
    ("Palestine", "Position on Palestine-related policy. TODO: replace with her specific stated position.", 3, None),
    ("Insurrection Act", "Supports constraining or reforming use of the Insurrection Act. TODO: replace with her specific stated position.", 3, None),
    ("Trump Accountability", "Supports legal/political accountability for Donald Trump. TODO: replace with her specific stated position.", 3, None),
    ("Government Corruption", "Supports rooting out government corruption. TODO: replace with her specific stated position.", 3, None),
    ("Election Reform", "Supports reforming election laws/processes. TODO: replace with her specific stated position.", 3, None),
    ("Bribery", "Supports anti-bribery enforcement and reform. TODO: replace with her specific stated position.", 3, None),
    ("Dark Money", "Supports campaign finance transparency and limiting dark money in politics. TODO: replace with her specific stated position.", 3, None),
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
            elif any("TODO" in summary for _, summary, _, _ in PLATFORM):
                print(
                    "Warning: PLATFORM still has placeholder ('TODO') summaries — replace them with "
                    "her actual stated positions before trusting alignment scores."
                )
            for topic, summary, priority, source in PLATFORM:
                existing = db.query(PlatformIssue).filter_by(official_id=official.id, topic=topic).one_or_none()
                if existing is None:
                    db.add(PlatformIssue(official_id=official.id, topic=topic, position_summary=summary, priority=priority, source_url=source))

        print(f"Seeded {args.politician} (official id={official.id}, opposition={args.opposition}).")


if __name__ == "__main__":
    main()
