"""Deterministic router: models propose, rules decide (ADR 0004).

Rules run in a fixed order and the first match wins. Every decision carries the
reasons that fired it, so a checker can see why a case landed where it did.
"""

from dataclasses import dataclass
from datetime import date

from app.pipeline.contracts import (
    ArchiveHit,
    ArchiveLabel,
    Claim,
    Duplicate,
    Evidence,
    MediaMatch,
    Route,
    RouteDecision,
    SourceKind,
    StageFailure,
    Stance,
    Verdict,
    VerdictLabel,
)

# Lower-case fragments of generator names that appear as visible watermarks.
AI_TOOL_MARKS = (
    "veo",
    "sora",
    "gemini",
    "runway",
    "kling",
    "pika",
    "hailuo",
    "midjourney",
    "dall-e",
    "meta ai",
    "grok",
)

REFUTING_LABELS = (VerdictLabel.FALSE, VerdictLabel.MISLEADING)


@dataclass(frozen=True)
class Thresholds:
    """Starting values; tuned on the eval tuning split for fast-track precision >= 0.95.

    Media values come from a robustness check on Creative Commons flood photos
    (docs/architecture.md 3.3): edited reposts scored pHash <= 15 or cosine >= 0.974,
    different photos of the same river scored pHash >= 26 and cosine up to 0.946.
    """

    phash_max_distance: int = 16
    cosine_min: float = 0.97
    fast_track_confidence: float = 0.85
    min_independent_sources: int = 2
    # Footage of one disaster keeps being reposted, correctly, for weeks after it.
    same_event_days: int = 30


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class StageOutputs:
    """Whatever the pipeline produced for one case. A stage that did not run is None."""

    failures: tuple[StageFailure, ...] = ()
    duplicate: Duplicate | None = None
    claim: Claim | None = None
    media_match: MediaMatch | None = None
    evidence: Evidence | None = None
    verdict: Verdict | None = None
    # When the post was made or submitted; dates archive footage that has no prior label.
    seen_on: date | None = None


def route(outputs: StageOutputs, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> RouteDecision:
    if outputs.failures:
        return RouteDecision(
            route=Route.HUMAN_REVIEW,
            reasons=[f"{f.stage} failed: {f.error}" for f in outputs.failures],
        )

    if outputs.duplicate is not None:
        dup = outputs.duplicate
        return RouteDecision(
            route=Route.MERGE,
            reasons=[f"same {dup.basis} as case {dup.case_id}"],
            merge_into=dup.case_id,
        )

    claim = _require(outputs.claim, "claim")
    if not claim.checkable:
        return RouteDecision(route=Route.DISMISS, reasons=["not a checkable factual claim"])

    media = _require(outputs.media_match, "media_match")
    evidence = _require(outputs.evidence, "evidence")
    verdict = _require(outputs.verdict, "verdict")
    if unknown := verdict.unknown_citations(evidence):
        # The verdict stage rejects these; reaching here means a pipeline bug.
        raise ValueError(f"verdict cites passages it was not given: {unknown}")

    strong_prior = recycled_hits(outputs, thresholds)
    ai_marks = _ai_tool_marks(claim)
    conflicts = _conflicts(verdict, evidence, strong_prior, ai_marks)
    label = verdict.label

    def decide(route: Route, reasons: list[str]) -> RouteDecision:
        return RouteDecision(route=route, reasons=reasons, proposed_label=label)

    if not conflicts and label in REFUTING_LABELS:
        if strong_prior:
            hit = strong_prior[0]
            return decide(Route.FAST_TRACK, [f"recycled media: matches {hit.original_context}"])
        if (
            ai_marks
            and not verdict.fallback
            and verdict.confidence >= thresholds.fast_track_confidence
        ):
            return decide(Route.FAST_TRACK, [f"visible ai-tool watermark: {', '.join(ai_marks)}"])

    agreeing = _agreeing_sources(verdict, evidence)
    confident = (
        not conflicts
        and not verdict.fallback
        and label is not VerdictLabel.UNVERIFIABLE
        and verdict.confidence >= thresholds.fast_track_confidence
    )
    if confident and (checkers := _agreeing_fact_checkers(verdict, evidence)):
        return decide(Route.FAST_TRACK, [f"prior fact-check agrees: {', '.join(checkers)}"])
    if confident and len(agreeing) >= thresholds.min_independent_sources:
        return decide(
            Route.FAST_TRACK,
            [f"strong evidence: {len(agreeing)} independent sources ({', '.join(agreeing)})"],
        )

    if not evidence.passages and not media.hits:
        return decide(Route.INVESTIGATE, ["new claim: no evidence and no archive match"])

    reasons = conflicts or [_why_not_confident(verdict, agreeing, thresholds)]
    return decide(Route.HUMAN_REVIEW, reasons)


def _require[T](value: T | None, name: str) -> T:
    if value is None:
        raise ValueError(f"{name} is missing but no stage failure was recorded")
    return value


def recycled_hits(outputs: StageOutputs, t: Thresholds = DEFAULT_THRESHOLDS) -> list[ArchiveHit]:
    """Strong archive matches showing the media predates the post (architecture 3.7)."""
    if outputs.media_match is None:
        return []
    # A date the post itself claims wins: "the 2024 flood" with 2024 footage is not recycled.
    claimed = outputs.claim.claimed_date if outputs.claim else None
    reference = claimed or outputs.seen_on
    return [
        hit
        for hit in outputs.media_match.hits
        if is_strong_match(hit, t) and _is_older_footage(hit, reference, t)
    ]


def is_strong_match(hit: ArchiveHit, t: Thresholds = DEFAULT_THRESHOLDS) -> bool:
    by_hash = hit.phash_distance is not None and hit.phash_distance <= t.phash_max_distance
    by_embedding = hit.cosine is not None and hit.cosine >= t.cosine_min
    return by_hash or by_embedding


def _is_older_footage(hit: ArchiveHit, reference: date | None, t: Thresholds) -> bool:
    """Prior footage, or genuine footage of an earlier event resurfacing under a new claim."""
    if hit.archive_label is ArchiveLabel.PRIOR:
        return True
    if hit.original_date is None or reference is None:
        return False
    return (reference - hit.original_date).days > t.same_event_days


def _ai_tool_marks(claim: Claim) -> list[str]:
    found: list[str] = []
    for mark in claim.watermarks:
        lowered = mark.lower()
        found.extend(tool for tool in AI_TOOL_MARKS if tool in lowered and tool not in found)
    return found


def _expected_stance(label: VerdictLabel) -> Stance | None:
    if label in REFUTING_LABELS:
        return Stance.REFUTES
    if label is VerdictLabel.TRUE:
        return Stance.SUPPORTS
    return None


def _agreeing_sources(verdict: Verdict, evidence: Evidence) -> list[str]:
    """Distinct sources whose cited passages agree with the verdict, in citation order."""
    expected = _expected_stance(verdict.label)
    sources: list[str] = []
    for citation in verdict.citations:
        passage = evidence.by_id(citation.passage_id)
        if passage and citation.stance is expected and passage.source not in sources:
            sources.append(passage.source)
    return sources


def _agreeing_fact_checkers(verdict: Verdict, evidence: Evidence) -> list[str]:
    expected = _expected_stance(verdict.label)
    checkers: list[str] = []
    for citation in verdict.citations:
        passage = evidence.by_id(citation.passage_id)
        if (
            passage
            and passage.source_kind is SourceKind.FACT_CHECK
            and citation.stance is expected
            and passage.source not in checkers
        ):
            checkers.append(passage.source)
    return checkers


def _conflicts(
    verdict: Verdict,
    evidence: Evidence,
    strong_prior: list[ArchiveHit],
    ai_marks: list[str],
) -> list[str]:
    conflicts: list[str] = []
    if verdict.label is VerdictLabel.TRUE:
        if strong_prior:
            conflicts.append(
                f"verdict is true but media matches {strong_prior[0].original_context}"
            )
        if ai_marks:
            marks = ", ".join(ai_marks)
            conflicts.append(f"verdict is true but ai-tool watermark visible: {marks}")

    expected = _expected_stance(verdict.label)
    if expected is not None:
        for citation in verdict.citations:
            passage = evidence.by_id(citation.passage_id)
            if passage and citation.stance is not expected:
                conflicts.append(f"cited {passage.source} {citation.stance} the claim")
    return conflicts


def _why_not_confident(verdict: Verdict, agreeing: list[str], t: Thresholds) -> str:
    if verdict.fallback:
        return f"drafted by the local fallback model ({verdict.model}); needs a human"
    if verdict.label is VerdictLabel.UNVERIFIABLE:
        return "ambiguous: evidence does not settle the claim"
    if verdict.confidence < t.fast_track_confidence:
        return f"ambiguous: confidence {verdict.confidence:g} below {t.fast_track_confidence:g}"
    return (
        f"ambiguous: {len(agreeing)} independent source(s), "
        f"{t.min_independent_sources} needed to fast-track"
    )
