"""One structured Claude pass over a video transcript: summary, key points, and
discrete proposed ideas worth tracking (as opposed to just prose)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from biopunk_media.analysis.llm import extract

SYSTEM_PROMPT = """You analyze transcripts of biotech founder presentations, pitches, \
and demo videos for the Biopunk accelerator's media team. Given a transcript, produce:

1. A concise summary (3-5 sentences) of what was presented.
2. Key points — the concrete facts/claims worth remembering (traction numbers, \
technical milestones, team notes), one per line, no more than 8.
3. Proposed ideas — distinct, concrete ideas, initiatives, or asks raised in the video \
that are worth tracking as follow-up items (e.g. "explore a partnership with X", \
"build a CRO service offering", "hire a wet-lab ops lead"). Each needs a short title \
(under 10 words) and a one-sentence description. Only include genuinely distinct, \
actionable ideas — skip restating the summary. It's fine to return zero if none stood out."""


class ExtractedIdea(BaseModel):
    title: str = Field(description="Short, specific idea title, under 10 words")
    description: str = Field(description="One sentence of context for the idea")


class VideoSummaryResult(BaseModel):
    summary: str
    key_points: list[str]
    proposed_ideas: list[ExtractedIdea]


def summarize_transcript(transcript_text: str, context: str = "") -> VideoSummaryResult:
    user = ""
    if context:
        user += f"Context: {context}\n\n"
    user += f"Transcript:\n{transcript_text}"
    return extract(SYSTEM_PROMPT, user, VideoSummaryResult, max_tokens=2048)
