"""Thin wrapper around the Anthropic client used by every analysis module."""
from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from civiclens.config import ANALYSIS_MODEL, ANTHROPIC_API_KEY

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else anthropic.Anthropic()
    return _client


def extract(system: str, user: str, schema: type[T], max_tokens: int = 4096) -> T:
    """One structured-extraction call: returns an instance of `schema`."""
    client = get_client()
    response = client.messages.parse(
        model=ANALYSIS_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    return response.parsed_output


def complete(system: str, user: str, max_tokens: int = 4096) -> str:
    """One free-text completion call."""
    client = get_client()
    response = client.messages.create(
        model=ANALYSIS_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")
