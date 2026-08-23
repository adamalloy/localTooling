# CivicLens

A local tool for analyzing Oakland (and, later, other district) city council meetings:
video/transcript ingestion, meeting summaries, topic and controversy trends, council
member accountability profiles, and evidence-based tracking of public testimony.

## Scope decision — read this first

This tool deliberately draws a line between **public officials** and **private
citizens who speak at public meetings**:

- **Officials** (council members, and the two reference politicians this tool tracks
  positions against) get full accountability profiles: votes, statements, and a score
  for how aligned their record is with a given platform issue. They're public figures;
  this is standard accountability work.
- **Private speakers** get an evidence log only — every statement they made, what topic
  and stance was extracted from it, and how often they've shown up. There is no
  automated psychological/behavioral labeling ("aggressive," "mainstream" vs "kooky")
  and no automated ally/opponent flag tied to a candidate. The `/search` page lets you
  filter statements by topic and stance (e.g. everything said in support of a platform
  issue), so you can see who's said something aligned with a position — but the
  judgment about who's an ally is yours, made by reading their actual words, not a
  label this tool assigns to a named private resident.

This was an explicit design decision (not an oversight) — see `civiclens/models.py`'s
module docstring for the reasoning. If you want the automated profiling/labeling
described in the original request instead, that's a deliberate change to make, not a
missing feature — ask and we can talk through it, but it isn't turned on by default.

## What's implemented

- **DB schema** (`civiclens/models.py`): cities, officials, platform issues, meetings,
  agenda items, speakers, statements, topic/stance links, votes, documents,
  meeting summaries, alignment scores, follow-up recommendations.
- **Ingestion** (`civiclens/ingestion/`):
  - Video → audio (ffmpeg) → transcription (faster-whisper, runs locally) → optional
    speaker diarization (pyannote.audio) → `Statement` rows.
  - Plain-text transcript ingestion (`SPEAKER: text` format) as an alternative to video.
  - Legistar Web API client for agendas/minutes/votes/attachments (see "Data sources").
  - Generic PDF/HTML document fetcher for budgets, reports, and policy documents.
- **Analysis** (`civiclens/analysis/`, via the Claude API):
  - Per-statement topic + stance extraction, with the source quote (`statement_analysis.py`).
  - Grievance detection — flags testimony describing concrete mistreatment by the
    city, without judging the speaker (`statement_analysis.py`).
  - Whole-meeting summary, key takeaways, controversial vs. consensus topics (`meeting_summary.py`).
  - Official alignment scoring against a reference politician's platform issues, and
    follow-up recommendations for engaging them (`alignment.py`).
- **Web app** (`civiclens/web/`, FastAPI + Jinja2): dashboard, meeting detail with
  transcript/summary, official profiles, public-speaker evidence pages, topic search,
  follow-up recommendation list.

## Not yet built (roadmap)

- Auto-matching a diarized "SPEAKER_00" turn to a known Speaker/Official across
  meetings (currently: a self-introduction heuristic *suggests* a name; you confirm
  it by hand — there's no UI for that confirmation yet, only direct DB edits).
- A UI for entering votes (currently: `Vote` rows have to be inserted directly, e.g.
  from Legistar `eventitems` data — no scraper writes them automatically yet).
- Multi-city rollup views (the schema supports multiple `City` rows now; the "profile
  per city" browsing exists via the `city_id` filters on `/`, `/officials`, `/speakers`,
  but there's no cross-city trends page yet).
- Chunking very long meeting transcripts before summarization (current cap is ~180K
  characters per call, generous for a single meeting but not for merging many).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum
```

You'll also need `ffmpeg` on your PATH for video ingestion (`brew install ffmpeg` /
`apt install ffmpeg`). Diarization (who-said-what) additionally needs a Hugging Face
token — see `.env.example`. Without it, video ingestion still works, but every
statement in a meeting is attributed to one "Unknown Speaker" until you split it by hand.

Run the web app:

```bash
uvicorn civiclens.web.app:app --reload
```

## Usage

```bash
# 1. Seed a city and a reference politician's platform (edit scripts/seed_platform.py
#    with her actual stated positions first — the PLATFORM list ships empty).
python scripts/seed_platform.py --city Oakland --politician "Jamie Joyce" --role "Councilmember"
python scripts/seed_platform.py --city Oakland --politician "Lateefah Simon" --opposition

# 2. Ingest a meeting from video (local file or URL) or an existing transcript file.
python scripts/ingest_meeting.py --city Oakland --date 2026-01-06 \
    --title "City Council Regular Meeting" --video ~/Downloads/meeting.mp4

# 3. Run LLM analysis (topic/stance extraction, grievances, meeting summary).
python scripts/run_analysis.py <meeting_id>

# 4. Browse at http://127.0.0.1:8000
```

Alignment scores and follow-up recommendations are generated per official/issue pair
via `civiclens.analysis.alignment.score_alignment` and `generate_follow_up` — call
these from a script once you've seeded platform issues and have votes/statements on
record for an official (no CLI wrapper for these two yet; straightforward to add).

## Data sources

Oakland runs its public meeting records on **Legistar**. `civiclens/ingestion/legistar.py`
targets the documented public Legistar Web API (`webapi.legistar.com/v1/{client}`), but
**the exact client slug and response shapes are unverified** — this was written without
network access to Oakland's site. Before relying on it:

```bash
curl https://webapi.legistar.com/v1/oakland/bodies
```

If that doesn't return Oakland's council/committee bodies, find the real client slug by
visiting `oakland.legistar.com` and checking what `webapi.legistar.com/v1/<name>` calls
its own frontend makes, then set `CIVICLENS_LEGISTAR_CLIENT` in `.env`.

Meeting video: Legistar events often link to a Granicus/city media player rather than a
directly downloadable file. `civiclens/ingestion/video_source.py` handles local files,
direct video URLs, and YouTube (Oakland publishes to a city YouTube channel) via
`yt-dlp`. If a specific meeting's video is only in Granicus's own player, download it
manually and pass the local file path instead.

## Extending to other cities in your district

The schema is already multi-city (`City` rows, everything else scoped by `city_id`).
To add another city: run `seed_platform.py` (or insert a `City` row directly) with its
name, and if it also runs Legistar, a separate `CIVICLENS_LEGISTAR_CLIENT` — otherwise
`civiclens/ingestion/legistar.py` won't apply and you'd feed that city's documents
through `civiclens/ingestion/documents.py` directly with its own source URLs.
