from __future__ import annotations

import datetime as dt
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from civiclens.analysis.meeting_summary import summarize_meeting
from civiclens.analysis.statement_analysis import analyze_meeting_statements
from civiclens.config import UPLOADS_DIR
from civiclens.db import session_scope
from civiclens.ingestion.pipeline import ingest_transcript_docx, ingest_transcript_text
from civiclens.models import (
    City,
    FollowUpRecommendation,
    Meeting,
    MeetingSummary,
    Official,
    OfficialAlignment,
    PlatformIssue,
    Speaker,
    SpeakerType,
    Statement,
    StatementTopic,
    Topic,
    Vote,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="CivicLens")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, city_id: int | None = None):
    with session_scope() as db:
        cities = db.query(City).order_by(City.name).all()
        meetings_q = db.query(Meeting).options(joinedload(Meeting.summary)).order_by(Meeting.meeting_date.desc())
        if city_id:
            meetings_q = meetings_q.filter(Meeting.city_id == city_id)
        meetings = meetings_q.limit(20).all()

        follow_ups_q = (
            db.query(FollowUpRecommendation)
            .options(joinedload(FollowUpRecommendation.official))
            .filter(FollowUpRecommendation.status == "open")
            .order_by(FollowUpRecommendation.priority.desc())
        )
        follow_ups = follow_ups_q.limit(10).all()

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"cities": cities, "meetings": meetings, "follow_ups": follow_ups, "selected_city_id": city_id},
        )


@app.get("/meetings/new", response_class=HTMLResponse)
def new_meeting_form(request: Request):
    with session_scope() as db:
        cities = db.query(City).order_by(City.name).all()
        return templates.TemplateResponse(request, "meeting_new.html", {"cities": cities, "error": None})


@app.post("/meetings/new")
async def create_meeting(
    request: Request,
    city_id: str = Form(""),
    new_city_name: str = Form(""),
    meeting_date: str = Form(...),
    title: str = Form(...),
    meeting_type: str = Form(""),
    transcript_file: UploadFile | None = File(None),
):
    error = None
    if not city_id.strip() and not new_city_name.strip():
        error = "Choose an existing city or enter a new city name."
    elif not transcript_file or not transcript_file.filename:
        error = "Choose a transcript file (.txt or .docx) to upload."
    elif not transcript_file.filename.lower().endswith((".txt", ".docx")):
        error = f"Unsupported file type: {transcript_file.filename}. Use .txt or .docx."

    if error:
        with session_scope() as db:
            cities = db.query(City).order_by(City.name).all()
            return templates.TemplateResponse(request, "meeting_new.html", {"cities": cities, "error": error})

    suffix = Path(transcript_file.filename).suffix.lower()
    dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(transcript_file.file, out)

    with session_scope() as db:
        if new_city_name.strip():
            city = db.query(City).filter_by(name=new_city_name.strip()).one_or_none()
            if city is None:
                city = City(name=new_city_name.strip())
                db.add(city)
                db.flush()
        else:
            city = db.get(City, int(city_id))

        parsed_date = dt.date.fromisoformat(meeting_date)
        if suffix == ".docx":
            meeting = ingest_transcript_docx(
                db, city.id, parsed_date, title, dest, meeting_type=meeting_type or None
            )
        else:
            meeting = ingest_transcript_text(
                db, city.id, parsed_date, title, dest.read_text(), meeting_type=meeting_type or None
            )
        meeting_id = meeting.id

    return RedirectResponse(f"/meetings/{meeting_id}", status_code=303)


@app.post("/meetings/{meeting_id}/analyze")
def run_meeting_analysis(meeting_id: int):
    """
    Runs LLM topic/stance/grievance extraction and the meeting summary synchronously.
    For a long meeting (hundreds of statements) this makes one API call per statement
    plus one summary call, so the request can take several minutes — the browser will
    just wait on it. Requires ANTHROPIC_API_KEY to be set.
    """
    with session_scope() as db:
        analyze_meeting_statements(db, meeting_id)
        summarize_meeting(db, meeting_id)
    return RedirectResponse(f"/meetings/{meeting_id}", status_code=303)


@app.get("/meetings/{meeting_id}", response_class=HTMLResponse)
def meeting_detail(request: Request, meeting_id: int):
    with session_scope() as db:
        meeting = (
            db.query(Meeting)
            .options(joinedload(Meeting.summary), joinedload(Meeting.city))
            .filter(Meeting.id == meeting_id)
            .one()
        )
        statements = (
            db.query(Statement)
            .options(joinedload(Statement.speaker), joinedload(Statement.topics).joinedload(StatementTopic.topic))
            .filter(Statement.meeting_id == meeting_id)
            .order_by(Statement.sequence)
            .all()
        )
        votes = (
            db.query(Vote)
            .options(joinedload(Vote.official))
            .filter(Vote.meeting_id == meeting_id)
            .all()
        )
        return templates.TemplateResponse(
            request,
            "meeting_detail.html",
            {"meeting": meeting, "statements": statements, "votes": votes},
        )


@app.get("/officials", response_class=HTMLResponse)
def officials_list(request: Request, city_id: int | None = None):
    with session_scope() as db:
        q = db.query(Official).options(joinedload(Official.city))
        if city_id:
            q = q.filter(Official.city_id == city_id)
        officials = q.order_by(Official.name).all()
        cities = db.query(City).order_by(City.name).all()
        return templates.TemplateResponse(
            request, "officials_list.html", {"officials": officials, "cities": cities, "selected_city_id": city_id}
        )


@app.get("/officials/{official_id}", response_class=HTMLResponse)
def official_detail(request: Request, official_id: int):
    with session_scope() as db:
        official = db.query(Official).filter(Official.id == official_id).one()
        alignments = (
            db.query(OfficialAlignment)
            .options(joinedload(OfficialAlignment.platform_issue))
            .filter(OfficialAlignment.official_id == official_id)
            .order_by(OfficialAlignment.alignment_score.desc())
            .all()
        )
        votes = (
            db.query(Vote)
            .options(joinedload(Vote.meeting), joinedload(Vote.agenda_item))
            .filter(Vote.official_id == official_id)
            .order_by(Vote.id.desc())
            .all()
        )
        statements = (
            db.query(Statement)
            .join(Speaker)
            .filter(Speaker.official_id == official_id)
            .options(joinedload(Statement.meeting), joinedload(Statement.topics).joinedload(StatementTopic.topic))
            .order_by(Statement.id.desc())
            .limit(50)
            .all()
        )
        follow_ups = (
            db.query(FollowUpRecommendation)
            .filter(FollowUpRecommendation.official_id == official_id)
            .order_by(FollowUpRecommendation.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            request,
            "official_detail.html",
            {"official": official, "alignments": alignments, "votes": votes, "statements": statements, "follow_ups": follow_ups},
        )


@app.get("/speakers", response_class=HTMLResponse)
def speakers_list(request: Request, city_id: int | None = None, q: str | None = Query(default=None)):
    with session_scope() as db:
        query = db.query(
            Speaker,
            func.count(Statement.id).label("statement_count"),
            func.count(func.distinct(Statement.meeting_id)).label("meeting_count"),
        ).outerjoin(Statement).filter(Speaker.speaker_type == SpeakerType.PUBLIC)
        if city_id:
            query = query.filter(Speaker.city_id == city_id)
        if q:
            query = query.filter(Speaker.name.ilike(f"%{q}%"))
        rows = query.group_by(Speaker.id).order_by(func.count(Statement.id).desc()).limit(100).all()
        cities = db.query(City).order_by(City.name).all()
        return templates.TemplateResponse(
            request,
            "speakers_list.html",
            {"rows": rows, "cities": cities, "selected_city_id": city_id, "q": q or ""},
        )


@app.get("/speakers/{speaker_id}", response_class=HTMLResponse)
def speaker_detail(request: Request, speaker_id: int):
    """
    Evidence page for one member of the public: every statement they made, the topics
    and stances extracted from those statements, and any grievances they raised.
    Intentionally has no summary judgment field — the reader draws their own conclusion.
    """
    with session_scope() as db:
        speaker = db.query(Speaker).filter(Speaker.id == speaker_id).one()
        statements = (
            db.query(Statement)
            .options(joinedload(Statement.meeting), joinedload(Statement.topics).joinedload(StatementTopic.topic))
            .filter(Statement.speaker_id == speaker_id)
            .order_by(Statement.id.desc())
            .all()
        )
        meeting_count = len({s.meeting_id for s in statements})
        grievances = [s for s in statements if s.contains_grievance]
        return templates.TemplateResponse(
            request,
            "speaker_detail.html",
            {"speaker": speaker, "statements": statements, "meeting_count": meeting_count, "grievances": grievances},
        )


@app.get("/search", response_class=HTMLResponse)
def search_by_topic(request: Request, topic: str | None = None, stance: str | None = None):
    """
    Find who has spoken about a topic and with what stance — e.g. filter to statements
    matching a platform issue you care about, to see who's said something aligned with
    it. Surfaces evidence (quotes, speaker, meeting); draws no ally/opponent conclusion.
    """
    results = []
    if topic:
        with session_scope() as db:
            q = (
                db.query(StatementTopic)
                .join(Topic)
                .join(Statement)
                .options(
                    joinedload(StatementTopic.statement).joinedload(Statement.speaker),
                    joinedload(StatementTopic.statement).joinedload(Statement.meeting),
                    joinedload(StatementTopic.topic),
                )
                .filter(Topic.name.ilike(f"%{topic}%"))
            )
            if stance:
                q = q.filter(StatementTopic.stance == stance)
            results = q.order_by(StatementTopic.confidence.desc()).limit(100).all()

    with session_scope() as db:
        return templates.TemplateResponse(
            request, "search.html", {"results": results, "topic": topic or "", "stance": stance or ""}
        )


@app.get("/follow-ups", response_class=HTMLResponse)
def follow_ups_list(request: Request):
    with session_scope() as db:
        follow_ups = (
            db.query(FollowUpRecommendation)
            .options(joinedload(FollowUpRecommendation.official))
            .order_by(FollowUpRecommendation.status, FollowUpRecommendation.priority.desc())
            .all()
        )
        return templates.TemplateResponse(request, "follow_ups.html", {"follow_ups": follow_ups})
