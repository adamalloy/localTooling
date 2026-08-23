#!/usr/bin/env python3
"""
Run LLM analysis on an ingested meeting: topic/stance/grievance extraction across the
whole transcript (one call per ~150K-char chunk — one call total for a typical
meeting), then a whole-meeting summary with controversy/consensus detection.

Usage: python scripts/run_analysis.py <meeting_id>
Requires ANTHROPIC_API_KEY (or an `ant auth login` profile) to be configured.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from civiclens.analysis.meeting_summary import summarize_meeting
from civiclens.analysis.topic_extraction import analyze_meeting_topics
from civiclens.db import session_scope


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    meeting_id = int(sys.argv[1])

    with session_scope() as db:
        n = analyze_meeting_topics(db, meeting_id)
        print(f"Extracted topics/grievances from {n} statement(s).")
        summarize_meeting(db, meeting_id)
        print("Meeting summary generated.")


if __name__ == "__main__":
    main()
