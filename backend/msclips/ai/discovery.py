"""AI clip discovery: Claude reads the timestamped transcript and proposes the best standalone clips.

Claude chooses *which* passages to use, by transcript segment ids. Exact cut points are then computed
here from word timestamps (snap to word and sentence boundaries), so timings are never invented.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from msclips.core.config import get_settings

log = logging.getLogger(__name__)

Category = Literal[
    "tip", "story", "insight", "opinion", "humor", "emotional", "surprising", "conclusion", "educational", "other"
]
Style = Literal["clean", "podcast", "energetic", "storytelling", "educational", "comedy", "cinematic"]

DEFAULT_WEIGHTS = {
    "hook": 0.25, "emotion": 0.15, "value": 0.20, "standalone": 0.20, "retention": 0.10, "shareability": 0.10,
}


class Scores(BaseModel):
    hook: int = Field(description="0-10: how strongly the first seconds grab attention")
    emotion: int = Field(description="0-10: emotional impact")
    value: int = Field(description="0-10: usefulness / insight for the viewer")
    standalone: int = Field(description="0-10: understandable without the rest of the video")
    retention: int = Field(description="0-10: likelihood viewers watch to the end")
    shareability: int = Field(description="0-10: likelihood viewers share or save it")


class ProposedClip(BaseModel):
    start_segment_id: int = Field(description="id of the first transcript segment of the clip")
    end_segment_id: int = Field(description="id of the last transcript segment of the clip (inclusive)")
    title: str = Field(description="short descriptive title, in the transcript's language")
    hook: str = Field(
        description="on-screen hook text (max ~10 words) in the transcript's language; must be truthful to what is said"
    )
    category: Category
    reason: str = Field(description="1-2 sentences on why this moment works as a short, in the transcript's language")
    scores: Scores
    confidence: float = Field(description="0-1: confidence this is a strong standalone clip")
    editing_style: Style


class DiscoveryResult(BaseModel):
    clips: list[ProposedClip]
    notes: str = Field(description="empty, or a short explanation, e.g. why fewer clips than requested were found")


SYSTEM = """You are a senior short-form video editor. You pick moments from long-form videos (podcasts, \
interviews, talks) that work as standalone vertical shorts for TikTok, Instagram Reels and YouTube Shorts.

Rules:
- Pick passages that make sense on their own: a complete thought, story, tip, argument or joke with its \
setup and payoff. Avoid passages that depend on earlier context unless the context is inside the clip.
- The clip should open strongly: ideally its first sentence is itself a hook (a claim, question, surprising \
statement or the start of a story). Do not start mid-sentence or end before the point lands.
- Respect the requested duration range. Use the segment timestamps to estimate duration.
- Clips must not overlap each other.
- Rank the clips best first. Be honest in scoring; do not inflate scores and never promise virality.
- Hooks and titles must reflect what the speaker actually says. Never invent claims, numbers or quotes.
- If the video does not contain enough good moments, return fewer clips and say why in notes."""


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def build_prompt(segments: list[dict], clip_count: int, min_s: float, max_s: float, language: str) -> str:
    lines = [f"[{seg['id']}] {_fmt(seg['start'])}-{_fmt(seg['end'])} {seg['text']}" for seg in segments]
    return (
        f"Transcript language: {language}. Total segments: {len(segments)}.\n"
        f"Find the {clip_count} best clips, each between {min_s:.0f} and {max_s:.0f} seconds long.\n\n"
        "Transcript (format: [segment id] start-end text):\n" + "\n".join(lines)
    )


@dataclass
class Candidate:
    rank: int
    title: str
    hook: str
    category: str
    reason: str
    scores: dict
    score: float
    confidence: float
    editing_style: str
    start_s: float
    end_s: float
    transcript_text: str


class DiscoveryError(Exception):
    pass


_SENTENCE_END = re.compile(r"[.!?…]['\")\]]*$")


def _words_between(segments: list[dict], a: int, b: int) -> list[dict]:
    return [w for seg in segments[a : b + 1] for w in seg["words"]]


def snap_boundaries(
    segments: list[dict], start_id: int, end_id: int, min_s: float, max_s: float, media_duration: float
) -> tuple[float, float, str] | None:
    """Turn a segment range into precise cut times on word boundaries, ending on a sentence end when possible.

    Returns (start, end, text) or None when no acceptable range exists.
    """
    n = len(segments)
    if not (0 <= start_id < n and 0 <= end_id < n) or end_id < start_id:
        return None
    # Extend the end forward (max 2 segments) until a sentence ends, if it fits the duration limit.
    b = end_id
    for _ in range(2):
        if _SENTENCE_END.search(segments[b]["text"]) or b + 1 >= n:
            break
        if segments[b + 1]["end"] - segments[start_id]["start"] > max_s * 1.1:
            break
        b += 1
    words = _words_between(segments, start_id, b)
    if not words:
        return None
    # Too long: cut back at the last sentence end that keeps us within max.
    t0 = words[0]["s"]
    if words[-1]["e"] - t0 > max_s * 1.1:
        cut = None
        for i, w in enumerate(words):
            if w["e"] - t0 > max_s * 1.1:
                break
            if _SENTENCE_END.search(w["w"]) and w["e"] - t0 >= min_s * 0.8:
                cut = i
        if cut is None:
            return None
        words = words[: cut + 1]
    first, last = words[0], words[-1]
    # Small padding so the first/last word is not clipped, without bleeding into neighbouring words.
    all_words = [w for seg in segments for w in seg["words"]]
    idx_first = next(i for i, w in enumerate(all_words) if w is first)
    idx_last = next(i for i, w in enumerate(all_words) if w is last)
    prev_end = all_words[idx_first - 1]["e"] if idx_first > 0 else 0.0
    next_start = all_words[idx_last + 1]["s"] if idx_last + 1 < len(all_words) else media_duration
    start = max(prev_end, first["s"] - 0.15, 0.0)
    end = min(next_start, last["e"] + 0.35, media_duration)
    if end - start < min_s * 0.8:
        return None
    text = " ".join(w["w"] for w in words)
    return round(start, 3), round(end, 3), text


def weighted_score(scores: dict, weights: dict | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    total = sum(w.values())
    return round(sum(max(0, min(10, scores.get(k, 0))) * v for k, v in w.items()) / total * 10, 1)


def _overlap(a: Candidate, start: float, end: float) -> float:
    inter = max(0.0, min(a.end_s, end) - max(a.start_s, start))
    return inter / max(1e-6, min(a.end_s - a.start_s, end - start))


def postprocess(
    result: DiscoveryResult, segments: list[dict], clip_count: int, min_s: float, max_s: float, media_duration: float
) -> list[Candidate]:
    out: list[Candidate] = []
    for clip in result.clips:
        snapped = snap_boundaries(segments, clip.start_segment_id, clip.end_segment_id, min_s, max_s, media_duration)
        if snapped is None:
            log.info("dropping clip %r: no valid boundaries", clip.title)
            continue
        start, end, text = snapped
        if any(_overlap(c, start, end) > 0.2 for c in out):
            log.info("dropping clip %r: overlaps a higher-ranked clip", clip.title)
            continue
        scores = clip.scores.model_dump()
        out.append(
            Candidate(
                rank=len(out) + 1, title=clip.title.strip()[:300], hook=clip.hook.strip(), category=clip.category,
                reason=clip.reason.strip(), scores=scores, score=weighted_score(scores),
                confidence=max(0.0, min(1.0, clip.confidence)), editing_style=clip.editing_style,
                start_s=start, end_s=end, transcript_text=text,
            )
        )
        if len(out) >= clip_count:
            break
    return out


def call_claude(prompt: str) -> tuple[DiscoveryResult, str, dict]:
    """One structured-output request to Claude. Returns (parsed result, model id, usage)."""
    import anthropic

    s = get_settings()
    try:
        client = anthropic.Anthropic(max_retries=3)
    except anthropic.AnthropicError as e:  # no credentials configured
        raise DiscoveryError(
            "AI clip discovery needs a Claude API key. Set ANTHROPIC_API_KEY for the worker and retry."
        ) from e
    try:
        with client.beta.messages.stream(
            model=s.anthropic_model,
            max_tokens=32000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=DiscoveryResult,
            output_config={"effort": s.anthropic_effort},
            thinking={"type": "adaptive"},
            # On a policy decline, let the API retry on a suitable fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
    except TypeError as e:
        # The SDK raises TypeError at request time when no credential source is configured.
        if "authentication" in str(e).lower():
            raise DiscoveryError(
                "AI clip discovery needs a Claude API key. Set ANTHROPIC_API_KEY for the worker and retry."
            ) from e
        raise
    except anthropic.AuthenticationError as e:
        raise DiscoveryError("The Claude API key was rejected. Check ANTHROPIC_API_KEY.") from e
    except anthropic.PermissionDeniedError as e:
        raise DiscoveryError(f"The Claude API key lacks access: {e.message}") from e
    except anthropic.BadRequestError as e:
        raise DiscoveryError(f"Claude API rejected the request: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise ConnectionError("Claude API rate limit reached; will retry.") from e  # retryable
    except anthropic.InternalServerError as e:
        raise ConnectionError(f"Claude API error {e.status_code}; will retry.") from e  # retryable
    except anthropic.APIConnectionError as e:
        raise ConnectionError(f"Could not reach the Claude API: {e}") from e  # retryable

    if msg.stop_reason == "refusal":
        raise DiscoveryError("The AI declined to analyse this transcript.")
    if msg.stop_reason == "max_tokens":
        raise DiscoveryError("The AI response was cut off. Try requesting fewer clips.")
    parsed = msg.parsed_output
    if parsed is None:
        raise DiscoveryError("The AI response could not be parsed.")
    usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    return parsed, msg.model, usage


def discover(
    segments: list[dict], language: str, clip_count: int, min_s: float, max_s: float, media_duration: float
) -> tuple[list[Candidate], str, dict, str]:
    """Blocking. Returns (candidates, notes, usage, model)."""
    # Ask for a few extra so enough remain after boundary validation and de-duplication.
    ask = min(clip_count + max(2, clip_count // 3), 60)
    parsed, model, usage = call_claude(build_prompt(segments, ask, min_s, max_s, language))
    candidates = postprocess(parsed, segments, clip_count, min_s, max_s, media_duration)
    return candidates, parsed.notes, usage, model
