#!/usr/bin/env python3
"""
Ingest one meeting into the database, from video or from an existing transcript.

Examples:
  # From a local video file, transcribing locally:
  python scripts/ingest_meeting.py --city Oakland --date 2026-01-06 \\
      --title "City Council Regular Meeting" --video ~/Downloads/meeting.mp4

  # From a YouTube archive URL:
  python scripts/ingest_meeting.py --city Oakland --date 2026-01-06 \\
      --title "City Council Regular Meeting" --video "https://youtube.com/watch?v=..."

  # From an already-transcribed text file (SPEAKER: text per line):
  python scripts/ingest_meeting.py --city Oakland --date 2026-01-06 \\
      --title "City Council Regular Meeting" --transcript-file minutes.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from civiclens.db import init_db, session_scope
from civiclens.ingestion.pipeline import ingest_meeting, ingest_transcript_text
from civiclens.models import City


def get_or_create_city(session, name: str) -> City:
    city = session.query(City).filter_by(name=name).one_or_none()
    if city is None:
        city = City(name=name)
        session.add(city)
        session.flush()
    return city


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--title", required=True)
    parser.add_argument("--meeting-type", default=None)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="Local file path or URL (YouTube supported)")
    src.add_argument("--transcript-file", help="Path to an existing transcript text file")
    args = parser.parse_args()

    init_db()
    meeting_date = dt.date.fromisoformat(args.date)

    with session_scope() as db:
        city = get_or_create_city(db, args.city)
        if args.video:
            meeting = ingest_meeting(
                db, city.id, meeting_date, args.title, args.video, meeting_type=args.meeting_type
            )
        else:
            text = Path(args.transcript_file).read_text()
            meeting = ingest_transcript_text(
                db, city.id, meeting_date, args.title, text, meeting_type=args.meeting_type
            )
        print(f"Ingested meeting id={meeting.id} status={meeting.status.value}")
        print(f"Next: python scripts/run_analysis.py {meeting.id}")


if __name__ == "__main__":
    main()
