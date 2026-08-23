"""
Client for the Legistar Web API (webapi.legistar.com) — the platform Oakland and many
other California cities publish agendas, minutes, votes, and attached documents (budgets,
reports, policy memos) through.

Unverified against the live site: this was written without network access to confirm
Oakland's exact client slug or response shapes. Before relying on it, check:
  curl https://webapi.legistar.com/v1/oakland/bodies
If that 404s, find Oakland's actual client name by visiting https://oakland.legistar.com
and looking for "webapi.legistar.com/v1/<name>" in page source or network requests, then
set CIVICLENS_LEGISTAR_CLIENT accordingly.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import requests

from civiclens.config import LEGISTAR_API_BASE


@dataclass
class LegistarEvent:
    id: int
    body_name: str
    date: dt.date
    agenda_url: str | None
    minutes_url: str | None
    video_url: str | None


@dataclass
class LegistarMatterAttachment:
    matter_id: int
    name: str
    url: str


def get_events(start_date: dt.date, end_date: dt.date) -> list[LegistarEvent]:
    """List council meetings (events) in a date range."""
    filter_clause = (
        f"EventDate ge datetime'{start_date.isoformat()}' and "
        f"EventDate le datetime'{end_date.isoformat()}'"
    )
    resp = requests.get(
        f"{LEGISTAR_API_BASE}/events",
        params={"$filter": filter_clause},
        timeout=30,
    )
    resp.raise_for_status()
    events = []
    for e in resp.json():
        events.append(
            LegistarEvent(
                id=e.get("EventId"),
                body_name=e.get("EventBodyName", ""),
                date=dt.date.fromisoformat(e["EventDate"][:10]) if e.get("EventDate") else start_date,
                agenda_url=e.get("EventAgendaFile"),
                minutes_url=e.get("EventMinutesFile"),
                video_url=e.get("EventVideoPath") or e.get("EventInSiteURL"),
            )
        )
    return events


def get_event_items(event_id: int) -> list[dict]:
    """Agenda items (and, after the meeting, vote results) for one event."""
    resp = requests.get(f"{LEGISTAR_API_BASE}/events/{event_id}/eventitems", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_matter_attachments(matter_id: int) -> list[LegistarMatterAttachment]:
    """Documents attached to a legislative matter — often includes budget/report PDFs."""
    resp = requests.get(f"{LEGISTAR_API_BASE}/matters/{matter_id}/attachments", timeout=30)
    resp.raise_for_status()
    return [
        LegistarMatterAttachment(matter_id=matter_id, name=a.get("MatterAttachmentName", ""), url=a.get("MatterAttachmentHyperlink", ""))
        for a in resp.json()
        if a.get("MatterAttachmentHyperlink")
    ]


def get_bodies() -> list[dict]:
    """Legislative bodies (e.g. 'City Council', 'Budget Committee') — useful for a sanity check."""
    resp = requests.get(f"{LEGISTAR_API_BASE}/bodies", timeout=30)
    resp.raise_for_status()
    return resp.json()
