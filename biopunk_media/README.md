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
  `MediaAsset` (a source video — presentation, pitch, demo day talk) and
  `ProposedIdea` (an idea extracted from a video, tracked with its own
  status). `MediaAsset` is scoped the same way as `ContentItem`.
- **Web app** (`biopunk_media/web/`, FastAPI + Jinja2):
  - `/calendar` — month grid of scheduled content, filterable by scope,
    status, platform.
  - `/content` — full backlog (including unscheduled ideas/drafts), same
    filters, plus an "unscheduled only" toggle.
  - `/content/new`, `/content/{id}`, `/content/{id}/edit` — create/view/edit
    a content item.
  - `/media` — video/media library, filterable by scope and transcript
    status; `/media/new` accepts either an uploaded file or an external
    link (YouTube embeds automatically). Each asset's detail page has a
    transcript pane (paste one, or see the status if it's queued for local
    transcription), a "Generate AI summary" button, and a proposed-ideas
    table with per-idea status you can update inline.
  - `/ideas` — every proposed idea across every video, in one filterable
    board — tracked separately from the AI summary text so re-summarizing
    a video never loses a status you've already set.
  - `/houses`, `/companies`, `/members` — rosters, each with a detail page
    showing everything scoped to it (content, media, and — for members —
    everything they personally own/are responsible for). `/companies/new`
    and `/companies/{id}/edit` create/edit a company profile.

### Video → transcript → summary → tracked ideas

Three ways to get a transcript onto a `MediaAsset`:
1. **Paste one you already have** — in the upload form, or later on the
   asset's detail page.
2. **Generate one locally** — `python scripts/transcribe_media.py --media-id N`
   (or `--all-pending` for everything without one). Runs local Whisper via
   `requirements-biopunk-media-video.txt` (heavy — pulls in torch) plus
   `ffmpeg` on your PATH. Deliberately a CLI script, not a web-app button:
   transcribing a long video can take minutes, and a browser tab shouldn't
   hang on that.
3. **Leave it blank** — the asset just sits with `transcript_status: none`
   until one of the above happens.

Once there's a transcript, "Generate AI summary" on the asset's page makes
one Claude call (needs `ANTHROPIC_API_KEY` — shared with civiclens's key,
see `.env.example`) that returns a summary, key points, and a list of
proposed ideas. New ideas get inserted as their own `ProposedIdea` rows;
re-running the summary later skips any idea whose title already matches one
you have, so a status you've set (`in_progress`, `shipped`, ...) is never
silently reset. Ideas can also be added by hand, no AI required.

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
pip install -r requirements-biopunk-media.txt   # web app + AI summaries
python scripts/seed_biopunk_ecosystem.py        # houses + placeholder companies/members/content
uvicorn biopunk_media.web.app:app --reload
```

Browse at http://127.0.0.1:8000. Data lives in `data/biopunk/biopunk_media.db`
(SQLite by default; override with `BIOPUNK_MEDIA_DATABASE_URL`) and uploaded
video files in `data/biopunk/uploads/videos/` (served at `/uploads/...`) —
both gitignored, nothing here gets committed.

Set `ANTHROPIC_API_KEY` in `.env` (repo root) to use "Generate AI summary".
For local video transcription, additionally: `pip install -r
requirements-biopunk-media-video.txt` and have `ffmpeg` on your PATH.

## Not yet built (roadmap)

- Photo support in the media library (currently video-shaped: an uploaded
  file or a link, a transcript, an AI summary — a photo just wants a caption
  and doesn't need any of the transcript/summary machinery).
- Per-platform scheduling/status (today a `ContentItem` has one status and
  one scheduled time shared across all its platforms; a post might need to
  go out on Instagram Tuesday and X Wednesday).
- Auth/multi-user — this is a local single-user tool for now, like the rest
  of this repo.
- Integration with the two adjacent GitHub projects tracking the Haus/Biopunk
  housing network (`ThatMrE/haus-fund`, `riaarora016/haus-fund-housing-network`)
  — worth checking for a shared data model before this grows much further.
