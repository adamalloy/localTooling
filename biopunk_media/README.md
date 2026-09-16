# Biopunk Media

A local media planning/calendar tool for the **Biopunk** ecosystem (Haus's
biotech founder accelerator — the fund, the residency houses, the wet-lab,
and the media engine documenting all of it). It tracks content — posts,
videos, articles, newsletters — scoped to a **member**, a **company**, a
**house**, or the **project** as a whole, on a shared calendar.

## What's here

- **DB schema** (`biopunk_media/models.py`): `House`, `Company`, `Member`,
  `SocialAccount`, and `ContentItem` (the calendar entry — title, content
  type, status, scheduled/published dates, owner, platforms, asset link,
  notes). Every `ContentItem` has a `scope_type` (`member` / `company` /
  `house` / `project`) + `scope_id` pointing at the owning row — see the
  module docstring for why that's a lightweight polymorphic association
  rather than three separate FKs.
- **Web app** (`biopunk_media/web/`, FastAPI + Jinja2):
  - `/calendar` — month grid of scheduled content, filterable by scope,
    status, platform.
  - `/content` — full backlog (including unscheduled ideas/drafts), same
    filters, plus an "unscheduled only" toggle.
  - `/content/new`, `/content/{id}`, `/content/{id}/edit` — create/view/edit
    a content item.
  - `/houses`, `/companies`, `/members` — rosters, each with a detail page
    showing everything scoped to it (and, for members, everything they
    personally own/are responsible for).

## Data model note — what's real vs. placeholder

The five houses seeded by `scripts/seed_biopunk_ecosystem.py` (PunkHaus,
FemHaus, SafeHaus, AlumHaus, and the Kobe cell & gene therapy house) are
based on what's publicly documented about the Biopunk residency network.
**Companies, members, and the one example content item are placeholder
rows, clearly marked in the seed script** — no current cohort roster was
confirmed from public sources when this was built. Replace them with the
real roster before using this for anything beyond a demo.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-biopunk-media.txt   # lighter than requirements.txt — no LLM/video deps
python scripts/seed_biopunk_ecosystem.py        # houses + placeholder companies/members/content
uvicorn biopunk_media.web.app:app --reload
```

Browse at http://127.0.0.1:8000. Data lives in `data/biopunk/biopunk_media.db`
(SQLite by default; override with `BIOPUNK_MEDIA_DATABASE_URL`).

## Not yet built (roadmap)

- Asset library (uploading/tagging photos, video, logos, bios) — the current
  `asset_url` field is just a link out to wherever the file already lives
  (Drive, Frame.io, etc.).
- Per-platform scheduling/status (today a `ContentItem` has one status and
  one scheduled time shared across all its platforms; a post might need to
  go out on Instagram Tuesday and X Wednesday).
- Auth/multi-user — this is a local single-user tool for now, like the rest
  of this repo.
- Integration with the two adjacent GitHub projects tracking the Haus/Biopunk
  housing network (`ThatMrE/haus-fund`, `riaarora016/haus-fund-housing-network`)
  — worth checking for a shared data model before this grows much further.
