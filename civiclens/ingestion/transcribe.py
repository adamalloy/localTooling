"""
Audio extraction, transcription, and speaker diarization.

Transcription runs locally via faster-whisper (no audio ever leaves the machine).
Diarization (who-spoke-when) is optional — it requires a Hugging Face token and a
one-time acceptance of pyannote's model terms. Without it, everything is attributed
to a single "Unknown Speaker" per meeting and must be split/labeled by hand in the
web UI; with it, turns are grouped by detected speaker automatically (still requires
a human to attach a name in the UI — the pipeline never guesses an identity from
voice alone).
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from civiclens.config import HUGGINGFACE_TOKEN, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_SIZE

log = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class DiarizedTurn:
    start: float
    end: float
    text: str
    speaker_label: str  # e.g. "SPEAKER_00" — a pipeline-local label, not an identity


def extract_audio(video_path: Path, out_path: Path, sample_rate: int = 16000) -> Path:
    """Extract mono PCM WAV audio from a video (or re-encode an audio file) via ffmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ac", "1", "-ar", str(sample_rate), "-vn",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed to extract audio from {video_path}:\n{result.stderr}")
    return out_path


def transcribe_audio(audio_path: Path) -> list[TranscriptSegment]:
    """Run faster-whisper locally over the audio file and return timestamped segments."""
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments, _info = model.transcribe(str(audio_path), vad_filter=True)
    return [TranscriptSegment(start=s.start, end=s.end, text=s.text.strip()) for s in segments]


def diarize_audio(audio_path: Path) -> list[tuple[float, float, str]] | None:
    """
    Run pyannote speaker diarization. Returns a list of (start, end, speaker_label)
    turns, or None if no Hugging Face token is configured (see config.HUGGINGFACE_TOKEN).
    """
    if not HUGGINGFACE_TOKEN:
        log.warning("HUGGINGFACE_TOKEN not set — skipping diarization, all speech goes to one speaker.")
        return None

    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=HUGGINGFACE_TOKEN
    )
    diarization = pipeline(str(audio_path))
    turns: list[tuple[float, float, str]] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append((turn.start, turn.end, speaker))
    return turns


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def merge_transcript_and_diarization(
    segments: list[TranscriptSegment],
    diarization: list[tuple[float, float, str]] | None,
) -> list[DiarizedTurn]:
    """
    Assign each Whisper segment to the diarized speaker turn it overlaps most with,
    then merge consecutive same-speaker segments into single turns.
    """
    if not diarization:
        merged_text = " ".join(s.text for s in segments)
        if not segments:
            return []
        return [DiarizedTurn(segments[0].start, segments[-1].end, merged_text, "UNKNOWN")]

    labeled: list[DiarizedTurn] = []
    for seg in segments:
        best_label, best_overlap = "UNKNOWN", 0.0
        for d_start, d_end, label in diarization:
            ov = _overlap(seg.start, seg.end, d_start, d_end)
            if ov > best_overlap:
                best_overlap, best_label = ov, label
        labeled.append(DiarizedTurn(seg.start, seg.end, seg.text, best_label))

    merged: list[DiarizedTurn] = []
    for turn in labeled:
        if merged and merged[-1].speaker_label == turn.speaker_label:
            prev = merged[-1]
            merged[-1] = DiarizedTurn(prev.start, turn.end, f"{prev.text} {turn.text}".strip(), prev.speaker_label)
        else:
            merged.append(turn)
    return merged
