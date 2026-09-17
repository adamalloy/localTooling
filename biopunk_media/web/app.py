from __future__ import annotations

import calendar as calendar_mod
import datetime as dt
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from biopunk_media.analysis.video_summary import summarize_transcript
from biopunk_media.config import ANTHROPIC_API_KEY, UPLOADS_DIR, VIDEOS_DIR
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
    IdeaStatus,
    Member,
    MediaAsset,
    MediaSourceType,
    Platform,
    ProposedIdea,
    ScopeType,
    SocialAccount,
    SummaryStatus,
    TranscriptSource,
    TranscriptStatus,
)

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Biopunk Media")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_db():
    with session_scope() as session:
        yield session


def scope_label(session: Session, scope_type: ScopeType, scope_id: int | None) -> str:
    if scope_type == ScopeType.PROJECT:
        return "Biopunk (project-wide)"
    if scope_type == ScopeType.HOUSE:
        obj = session.get(House, scope_id)
        return obj.name if obj else "(deleted house)"
    if scope_type == ScopeType.COMPANY:
        obj = session.get(Company, scope_id)
        return obj.name if obj else "(deleted company)"
    if scope_type == ScopeType.MEMBER:
        obj = session.get(Member, scope_id)
        return obj.name if obj else "(deleted member)"
    return "?"


def scope_url(scope_type: ScopeType, scope_id: int | None) -> str | None:
    if scope_type == ScopeType.HOUSE and scope_id:
        return f"/houses/{scope_id}"
    if scope_type == ScopeType.COMPANY and scope_id:
        return f"/companies/{scope_id}"
    if scope_type == ScopeType.MEMBER and scope_id:
        return f"/members/{scope_id}"
    return None


def enrich(session: Session, items: list[ContentItem]) -> list[dict]:
    out = []
    for item in items:
        out.append(
            {
                "item": item,
                "scope_label": scope_label(session, item.scope_type, item.scope_id),
                "scope_url": scope_url(item.scope_type, item.scope_id),
                "platforms": [p.platform.value for p in item.platforms],
            }
        )
    return out


def enrich_media(session: Session, assets: list[MediaAsset]) -> list[dict]:
    return [
        {
            "asset": a,
            "scope_label": scope_label(session, a.scope_type, a.scope_id),
            "scope_url": scope_url(a.scope_type, a.scope_id),
        }
        for a in assets
    ]


def youtube_embed_url(url: str) -> str | None:
    if "youtube.com/watch?v=" in url:
        video_id = url.split("watch?v=")[1].split("&")[0]
        return f"https://www.youtube.com/embed/{video_id}"
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
        return f"https://www.youtube.com/embed/{video_id}"
    return None


templates.env.filters["youtube_embed_url"] = youtube_embed_url


# ---------------------------------------------------------------- home / calendar


@app.get("/")
def home():
    return RedirectResponse("/calendar")


@app.get("/calendar")
def calendar_view(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    scope_type: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    db: Session = Depends(get_db),
):
    today = dt.date.today()
    year = year or today.year
    month = month or today.month

    first_day = dt.date(year, month, 1)
    days_in_month = calendar_mod.monthrange(year, month)[1]
    last_day = dt.date(year, month, days_in_month)

    query = select(ContentItem).where(
        ContentItem.scheduled_at >= dt.datetime.combine(first_day, dt.time.min),
        ContentItem.scheduled_at <= dt.datetime.combine(last_day, dt.time.max),
    )
    if scope_type:
        query = query.where(ContentItem.scope_type == ScopeType(scope_type))
    if status:
        query = query.where(ContentItem.status == ContentStatus(status))
    items = list(db.scalars(query))
    if platform:
        wanted = Platform(platform)
        items = [i for i in items if any(p.platform == wanted for p in i.platforms)]

    by_day: dict[int, list[dict]] = {d: [] for d in range(1, days_in_month + 1)}
    for row in enrich(db, items):
        day = row["item"].scheduled_at.day
        by_day[day].append(row)

    # calendar grid: list of weeks, each a list of (day_number_or_None)
    cal = calendar_mod.Calendar(firstweekday=6)  # Sunday-first
    weeks = cal.monthdayscalendar(year, month)

    prev_month = (month - 1) or 12
    prev_year = year - 1 if month == 1 else year
    next_month = (month % 12) + 1
    next_year = year + 1 if month == 12 else year

    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "year": year,
            "month": month,
            "month_name": calendar_mod.month_name[month],
            "weeks": weeks,
            "by_day": by_day,
            "today": today,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "scope_types": list(ScopeType),
            "statuses": list(ContentStatus),
            "platforms": list(Platform),
            "f_scope_type": scope_type or "",
            "f_status": status or "",
            "f_platform": platform or "",
        },
    )


# ---------------------------------------------------------------- content backlog


@app.get("/content")
def content_list(
    request: Request,
    scope_type: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    unscheduled: bool | None = None,
    db: Session = Depends(get_db),
):
    query = select(ContentItem).order_by(
        ContentItem.scheduled_at.is_(None).desc(), ContentItem.scheduled_at, ContentItem.created_at.desc()
    )
    if scope_type:
        query = query.where(ContentItem.scope_type == ScopeType(scope_type))
    if status:
        query = query.where(ContentItem.status == ContentStatus(status))
    if unscheduled:
        query = query.where(ContentItem.scheduled_at.is_(None))
    items = list(db.scalars(query))
    if platform:
        wanted = Platform(platform)
        items = [i for i in items if any(p.platform == wanted for p in i.platforms)]

    return templates.TemplateResponse(
        request,
        "content_list.html",
        {
            "rows": enrich(db, items),
            "scope_types": list(ScopeType),
            "statuses": list(ContentStatus),
            "platforms": list(Platform),
            "f_scope_type": scope_type or "",
            "f_status": status or "",
            "f_platform": platform or "",
            "f_unscheduled": bool(unscheduled),
        },
    )


def _form_context(db: Session) -> dict:
    return {
        "content_types": list(ContentType),
        "statuses": list(ContentStatus),
        "scope_types": list(ScopeType),
        "platforms": list(Platform),
        "houses": list(db.scalars(select(House).order_by(House.name))),
        "companies": list(db.scalars(select(Company).order_by(Company.name))),
        "members": list(db.scalars(select(Member).order_by(Member.name))),
    }


@app.get("/content/new")
def content_new_form(request: Request, db: Session = Depends(get_db)):
    ctx = _form_context(db)
    ctx["item"] = None
    ctx["selected_platforms"] = []
    return templates.TemplateResponse(request, "content_form.html", ctx)


@app.post("/content/new")
def content_new_submit(
    title: str = Form(...),
    summary: str = Form(""),
    content_type: str = Form(...),
    scope_type: str = Form(...),
    scope_house_id: str = Form(""),
    scope_company_id: str = Form(""),
    scope_member_id: str = Form(""),
    status: str = Form(...),
    owner_member_id: str = Form(""),
    scheduled_at: str = Form(""),
    asset_url: str = Form(""),
    notes: str = Form(""),
    platforms: list[str] = Form([]),
    db: Session = Depends(get_db),
):
    scope_id = _resolve_scope_id(scope_type, scope_house_id, scope_company_id, scope_member_id)
    item = ContentItem(
        title=title.strip(),
        summary=summary.strip() or None,
        content_type=ContentType(content_type),
        scope_type=ScopeType(scope_type),
        scope_id=scope_id,
        status=ContentStatus(status),
        owner_member_id=int(owner_member_id) if owner_member_id else None,
        scheduled_at=_parse_dt(scheduled_at),
        asset_url=asset_url.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(item)
    db.flush()
    for p in platforms:
        db.add(ContentItemPlatform(content_item_id=item.id, platform=Platform(p)))
    db.flush()
    return RedirectResponse(f"/content/{item.id}", status_code=303)


def _resolve_scope_id(scope_type: str, house_id: str, company_id: str, member_id: str) -> int | None:
    st = ScopeType(scope_type)
    if st == ScopeType.HOUSE:
        return int(house_id) if house_id else None
    if st == ScopeType.COMPANY:
        return int(company_id) if company_id else None
    if st == ScopeType.MEMBER:
        return int(member_id) if member_id else None
    return None


def _parse_dt(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


@app.get("/content/{item_id}")
def content_detail(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(404, "Content item not found")
    row = enrich(db, [item])[0]
    return templates.TemplateResponse(
        request,
        "content_detail.html",
        {"row": row, "statuses": list(ContentStatus)},
    )


@app.get("/content/{item_id}/edit")
def content_edit_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(404, "Content item not found")
    ctx = _form_context(db)
    ctx["item"] = item
    ctx["selected_platforms"] = [p.platform.value for p in item.platforms]
    return templates.TemplateResponse(request, "content_form.html", ctx)


@app.post("/content/{item_id}/edit")
def content_edit_submit(
    item_id: int,
    title: str = Form(...),
    summary: str = Form(""),
    content_type: str = Form(...),
    scope_type: str = Form(...),
    scope_house_id: str = Form(""),
    scope_company_id: str = Form(""),
    scope_member_id: str = Form(""),
    status: str = Form(...),
    owner_member_id: str = Form(""),
    scheduled_at: str = Form(""),
    asset_url: str = Form(""),
    notes: str = Form(""),
    platforms: list[str] = Form([]),
    db: Session = Depends(get_db),
):
    item = db.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(404, "Content item not found")
    scope_id = _resolve_scope_id(scope_type, scope_house_id, scope_company_id, scope_member_id)
    item.title = title.strip()
    item.summary = summary.strip() or None
    item.content_type = ContentType(content_type)
    item.scope_type = ScopeType(scope_type)
    item.scope_id = scope_id
    item.status = ContentStatus(status)
    item.owner_member_id = int(owner_member_id) if owner_member_id else None
    item.scheduled_at = _parse_dt(scheduled_at)
    if item.status == ContentStatus.PUBLISHED and item.published_at is None:
        item.published_at = dt.datetime.utcnow()
    item.asset_url = asset_url.strip() or None
    item.notes = notes.strip() or None

    for existing in list(item.platforms):
        db.delete(existing)
    db.flush()
    for p in platforms:
        db.add(ContentItemPlatform(content_item_id=item.id, platform=Platform(p)))
    db.flush()
    return RedirectResponse(f"/content/{item.id}", status_code=303)


@app.post("/content/{item_id}/delete")
def content_delete(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ContentItem, item_id)
    if item:
        db.delete(item)
    return RedirectResponse("/content", status_code=303)


# ---------------------------------------------------------------- houses


@app.get("/houses")
def houses_list(request: Request, db: Session = Depends(get_db)):
    houses = list(db.scalars(select(House).order_by(House.name)))
    return templates.TemplateResponse(request, "houses_list.html", {"houses": houses})


@app.get("/houses/{house_id}")
def house_detail(house_id: int, request: Request, db: Session = Depends(get_db)):
    house = db.get(House, house_id)
    if house is None:
        raise HTTPException(404, "House not found")
    content = list(
        db.scalars(
            select(ContentItem)
            .where(ContentItem.scope_type == ScopeType.HOUSE, ContentItem.scope_id == house_id)
            .order_by(ContentItem.scheduled_at.is_(None), ContentItem.scheduled_at.desc())
        )
    )
    media = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.scope_type == ScopeType.HOUSE, MediaAsset.scope_id == house_id)
            .order_by(MediaAsset.created_at.desc())
        )
    )
    socials = list(
        db.scalars(
            select(SocialAccount).where(
                SocialAccount.owner_type == ScopeType.HOUSE, SocialAccount.owner_id == house_id
            )
        )
    )
    return templates.TemplateResponse(
        request,
        "house_detail.html",
        {"house": house, "rows": enrich(db, content), "media": media, "socials": socials},
    )


# ---------------------------------------------------------------- companies


@app.get("/companies")
def companies_list(request: Request, db: Session = Depends(get_db)):
    companies = list(db.scalars(select(Company).order_by(Company.name)))
    return templates.TemplateResponse(request, "companies_list.html", {"companies": companies})


def _company_form_context(db: Session) -> dict:
    return {
        "stages": list(CompanyStage),
        "houses": list(db.scalars(select(House).order_by(House.name))),
    }


@app.get("/companies/new")
def company_new_form(request: Request, db: Session = Depends(get_db)):
    ctx = _company_form_context(db)
    ctx["company"] = None
    return templates.TemplateResponse(request, "company_form.html", ctx)


@app.post("/companies/new")
def company_new_submit(
    name: str = Form(...),
    house_id: str = Form(""),
    stage: str = Form(...),
    cohort: str = Form(""),
    website: str = Form(""),
    one_liner: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    company = Company(
        name=name.strip(),
        slug=_slugify(db, Company, name),
        house_id=int(house_id) if house_id else None,
        stage=CompanyStage(stage),
        cohort=cohort.strip() or None,
        website=website.strip() or None,
        one_liner=one_liner.strip() or None,
        description=description.strip() or None,
    )
    db.add(company)
    db.flush()
    return RedirectResponse(f"/companies/{company.id}", status_code=303)


def _slugify(db: Session, model, name: str) -> str:
    base = "-".join(name.lower().split())
    base = "".join(c for c in base if c.isalnum() or c == "-") or "item"
    slug = base
    n = 2
    while db.query(model).filter_by(slug=slug).first() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


@app.get("/companies/{company_id}")
def company_detail(company_id: int, request: Request, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    content = list(
        db.scalars(
            select(ContentItem)
            .where(ContentItem.scope_type == ScopeType.COMPANY, ContentItem.scope_id == company_id)
            .order_by(ContentItem.scheduled_at.is_(None), ContentItem.scheduled_at.desc())
        )
    )
    media = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.scope_type == ScopeType.COMPANY, MediaAsset.scope_id == company_id)
            .order_by(MediaAsset.created_at.desc())
        )
    )
    socials = list(
        db.scalars(
            select(SocialAccount).where(
                SocialAccount.owner_type == ScopeType.COMPANY, SocialAccount.owner_id == company_id
            )
        )
    )
    return templates.TemplateResponse(
        request,
        "company_detail.html",
        {"company": company, "rows": enrich(db, content), "media": media, "socials": socials},
    )


@app.get("/companies/{company_id}/edit")
def company_edit_form(company_id: int, request: Request, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    ctx = _company_form_context(db)
    ctx["company"] = company
    return templates.TemplateResponse(request, "company_form.html", ctx)


@app.post("/companies/{company_id}/edit")
def company_edit_submit(
    company_id: int,
    name: str = Form(...),
    house_id: str = Form(""),
    stage: str = Form(...),
    cohort: str = Form(""),
    website: str = Form(""),
    one_liner: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    company.name = name.strip()
    company.house_id = int(house_id) if house_id else None
    company.stage = CompanyStage(stage)
    company.cohort = cohort.strip() or None
    company.website = website.strip() or None
    company.one_liner = one_liner.strip() or None
    company.description = description.strip() or None
    return RedirectResponse(f"/companies/{company.id}", status_code=303)


# ---------------------------------------------------------------- members


@app.get("/members")
def members_list(request: Request, db: Session = Depends(get_db)):
    members = list(db.scalars(select(Member).order_by(Member.name)))
    return templates.TemplateResponse(request, "members_list.html", {"members": members})


@app.get("/members/{member_id}")
def member_detail(member_id: int, request: Request, db: Session = Depends(get_db)):
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(404, "Member not found")
    content = list(
        db.scalars(
            select(ContentItem)
            .where(ContentItem.scope_type == ScopeType.MEMBER, ContentItem.scope_id == member_id)
            .order_by(ContentItem.scheduled_at.is_(None), ContentItem.scheduled_at.desc())
        )
    )
    owned = list(
        db.scalars(
            select(ContentItem)
            .where(ContentItem.owner_member_id == member_id)
            .order_by(ContentItem.scheduled_at.is_(None), ContentItem.scheduled_at.desc())
        )
    )
    media = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.scope_type == ScopeType.MEMBER, MediaAsset.scope_id == member_id)
            .order_by(MediaAsset.created_at.desc())
        )
    )
    socials = list(
        db.scalars(
            select(SocialAccount).where(
                SocialAccount.owner_type == ScopeType.MEMBER, SocialAccount.owner_id == member_id
            )
        )
    )
    return templates.TemplateResponse(
        request,
        "member_detail.html",
        {
            "member": member,
            "rows": enrich(db, content),
            "owned": enrich(db, owned),
            "media": media,
            "socials": socials,
        },
    )


# ---------------------------------------------------------------- media assets


@app.get("/media")
def media_list(
    request: Request,
    scope_type: str | None = None,
    transcript_status: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(MediaAsset).order_by(MediaAsset.created_at.desc())
    if scope_type:
        query = query.where(MediaAsset.scope_type == ScopeType(scope_type))
    if transcript_status:
        query = query.where(MediaAsset.transcript_status == TranscriptStatus(transcript_status))
    assets = list(db.scalars(query))
    return templates.TemplateResponse(
        request,
        "media_list.html",
        {
            "rows": enrich_media(db, assets),
            "scope_types": list(ScopeType),
            "transcript_statuses": list(TranscriptStatus),
            "f_scope_type": scope_type or "",
            "f_transcript_status": transcript_status or "",
        },
    )


def _media_form_context(db: Session) -> dict:
    return {
        "scope_types": list(ScopeType),
        "houses": list(db.scalars(select(House).order_by(House.name))),
        "companies": list(db.scalars(select(Company).order_by(Company.name))),
        "members": list(db.scalars(select(Member).order_by(Member.name))),
    }


@app.get("/media/new")
def media_new_form(
    request: Request,
    scope_type: str | None = None,
    scope_id: int | None = None,
    db: Session = Depends(get_db),
):
    ctx = _media_form_context(db)
    ctx["asset"] = None
    ctx["default_scope_type"] = scope_type or ""
    ctx["default_scope_id"] = scope_id or ""
    return templates.TemplateResponse(request, "media_form.html", ctx)


@app.post("/media/new")
async def media_new_submit(
    title: str = Form(...),
    scope_type: str = Form(...),
    scope_house_id: str = Form(""),
    scope_company_id: str = Form(""),
    scope_member_id: str = Form(""),
    source_type: str = Form(...),
    external_url: str = Form(""),
    transcript_text: str = Form(""),
    notes: str = Form(""),
    file: UploadFile | None = None,
    db: Session = Depends(get_db),
):
    scope_id = _resolve_scope_id(scope_type, scope_house_id, scope_company_id, scope_member_id)

    file_path = None
    original_filename = None
    resolved_source = MediaSourceType(source_type)
    if resolved_source == MediaSourceType.UPLOAD:
        if not file or not file.filename:
            raise HTTPException(400, "Choose a file to upload, or switch to 'Link'.")
        ext = Path(file.filename).suffix
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = VIDEOS_DIR / stored_name
        with open(dest, "wb") as out:
            while chunk := await file.read(1 << 20):
                out.write(chunk)
        file_path = f"videos/{stored_name}"
        original_filename = file.filename
        external_url = None
    else:
        if not external_url.strip():
            raise HTTPException(400, "Enter a URL, or switch to 'Upload a file'.")
        external_url = external_url.strip()

    asset = MediaAsset(
        title=title.strip(),
        scope_type=ScopeType(scope_type),
        scope_id=scope_id,
        source_type=resolved_source,
        file_path=file_path,
        original_filename=original_filename,
        external_url=external_url or None,
        notes=notes.strip() or None,
    )
    if transcript_text.strip():
        asset.transcript_text = transcript_text.strip()
        asset.transcript_source = TranscriptSource.PROVIDED
        asset.transcript_status = TranscriptStatus.READY
    db.add(asset)
    db.flush()
    return RedirectResponse(f"/media/{asset.id}", status_code=303)


@app.get("/media/{media_id}")
def media_detail(media_id: int, request: Request, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    ideas = list(
        db.scalars(
            select(ProposedIdea)
            .where(ProposedIdea.media_asset_id == media_id)
            .order_by(ProposedIdea.created_at)
        )
    )
    return templates.TemplateResponse(
        request,
        "media_detail.html",
        {
            "asset": asset,
            "scope_label": scope_label(db, asset.scope_type, asset.scope_id),
            "scope_url": scope_url(asset.scope_type, asset.scope_id),
            "key_points": (asset.key_points or "").splitlines(),
            "ideas": ideas,
            "idea_statuses": list(IdeaStatus),
            "has_anthropic": bool(ANTHROPIC_API_KEY),
        },
    )


@app.get("/media/{media_id}/edit")
def media_edit_form(media_id: int, request: Request, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    ctx = _media_form_context(db)
    ctx["asset"] = asset
    return templates.TemplateResponse(request, "media_form.html", ctx)


@app.post("/media/{media_id}/edit")
def media_edit_submit(
    media_id: int,
    title: str = Form(...),
    scope_type: str = Form(...),
    scope_house_id: str = Form(""),
    scope_company_id: str = Form(""),
    scope_member_id: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    scope_id = _resolve_scope_id(scope_type, scope_house_id, scope_company_id, scope_member_id)
    asset.title = title.strip()
    asset.scope_type = ScopeType(scope_type)
    asset.scope_id = scope_id
    asset.notes = notes.strip() or None
    return RedirectResponse(f"/media/{asset.id}", status_code=303)


@app.post("/media/{media_id}/delete")
def media_delete(media_id: int, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    if asset:
        if asset.source_type == MediaSourceType.UPLOAD and asset.file_path:
            (UPLOADS_DIR / asset.file_path).unlink(missing_ok=True)
        db.delete(asset)
    return RedirectResponse("/media", status_code=303)


@app.post("/media/{media_id}/transcript")
def media_transcript_submit(
    media_id: int,
    transcript_text: str = Form(...),
    db: Session = Depends(get_db),
):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    asset.transcript_text = transcript_text.strip()
    asset.transcript_source = TranscriptSource.PROVIDED
    asset.transcript_status = TranscriptStatus.READY if transcript_text.strip() else TranscriptStatus.NONE
    return RedirectResponse(f"/media/{asset.id}", status_code=303)


@app.post("/media/{media_id}/summarize")
def media_summarize(media_id: int, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    if not asset.transcript_text:
        raise HTTPException(400, "No transcript yet — add one before generating a summary.")

    context = f"Video title: {asset.title}. Scope: {scope_label(db, asset.scope_type, asset.scope_id)}."
    try:
        result = summarize_transcript(asset.transcript_text, context=context)
    except Exception as e:
        asset.summary_status = SummaryStatus.FAILED
        asset.notes = (asset.notes or "") + f"\n[summary generation failed: {e}]"
        return RedirectResponse(f"/media/{asset.id}", status_code=303)

    asset.summary = result.summary
    asset.key_points = "\n".join(result.key_points)
    asset.summary_status = SummaryStatus.READY
    asset.summary_generated_at = dt.datetime.utcnow()
    db.flush()

    existing_titles = {i.title.strip().lower() for i in asset.ideas}
    for idea in result.proposed_ideas:
        if idea.title.strip().lower() in existing_titles:
            continue
        db.add(
            ProposedIdea(
                media_asset_id=asset.id,
                title=idea.title.strip(),
                description=idea.description.strip(),
                source="ai",
            )
        )
    return RedirectResponse(f"/media/{asset.id}", status_code=303)


@app.post("/media/{media_id}/ideas")
def idea_add(
    media_id: int,
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    db.add(
        ProposedIdea(
            media_asset_id=media_id,
            title=title.strip(),
            description=description.strip() or None,
            source="manual",
        )
    )
    return RedirectResponse(f"/media/{media_id}", status_code=303)


# ---------------------------------------------------------------- proposed ideas board


@app.get("/ideas")
def ideas_board(
    request: Request,
    status: str | None = None,
    scope_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(ProposedIdea).join(MediaAsset).order_by(ProposedIdea.created_at.desc())
    if status:
        query = query.where(ProposedIdea.status == IdeaStatus(status))
    if scope_type:
        query = query.where(MediaAsset.scope_type == ScopeType(scope_type))
    ideas = list(db.scalars(query))
    rows = [
        {
            "idea": idea,
            "asset": idea.media_asset,
            "scope_label": scope_label(db, idea.media_asset.scope_type, idea.media_asset.scope_id),
        }
        for idea in ideas
    ]
    return templates.TemplateResponse(
        request,
        "ideas_list.html",
        {
            "rows": rows,
            "statuses": list(IdeaStatus),
            "scope_types": list(ScopeType),
            "f_status": status or "",
            "f_scope_type": scope_type or "",
        },
    )


@app.post("/ideas/{idea_id}/status")
def idea_status_update(idea_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    idea = db.get(ProposedIdea, idea_id)
    if idea is None:
        raise HTTPException(404, "Idea not found")
    idea.status = IdeaStatus(status)
    media_asset_id = idea.media_asset_id
    return RedirectResponse(f"/media/{media_asset_id}", status_code=303)


@app.post("/ideas/{idea_id}/delete")
def idea_delete(idea_id: int, db: Session = Depends(get_db)):
    idea = db.get(ProposedIdea, idea_id)
    if idea:
        media_asset_id = idea.media_asset_id
        db.delete(idea)
        return RedirectResponse(f"/media/{media_asset_id}", status_code=303)
    return RedirectResponse("/ideas", status_code=303)
