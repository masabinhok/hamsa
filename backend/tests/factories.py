"""Builders for valid stage outputs; tests override only the fields they care about."""

from typing import Any

from app.pipeline.contracts import (
    ArchiveHit,
    Citation,
    Claim,
    Evidence,
    MediaMatch,
    Passage,
    Verdict,
)
from app.router.route import StageOutputs


def claim(**overrides: Any) -> Claim:
    fields: dict[str, Any] = {
        "claim": "मेलम्ची बजार बगायो",
        "claim_en": "Melamchi bazaar was swept away",
        "places": ["Melamchi"],
        "checkable": True,
    }
    return Claim.model_validate(fields | overrides)


def hit(**overrides: Any) -> ArchiveHit:
    fields: dict[str, Any] = {
        "archive_id": "arc-1",
        "frame_index": 0,
        "phash_distance": 4,
        "archive_label": "prior",
        "original_context": "2023 Himachal Pradesh floods, Kullu",
        "source_url": "https://www.youtube.com/watch?v=abc",
    }
    return ArchiveHit.model_validate(fields | overrides)


def passage(passage_id: str, source: str, **overrides: Any) -> Passage:
    fields: dict[str, Any] = {
        "passage_id": passage_id,
        "source": source,
        "source_kind": "news",
        "url": f"https://example.org/{passage_id}",
        "text": "Reporting on the Melamchi flood.",
        "score": 0.8,
    }
    return Passage.model_validate(fields | overrides)


def verdict(label: str = "false", confidence: float = 0.9, **overrides: Any) -> Verdict:
    fields: dict[str, Any] = {
        "label": label,
        "confidence": confidence,
        "rationale_en": "The footage predates the incident.",
        "rationale_ne": "यो भिडियो पुरानो हो।",
        "model": "openai/gpt-oss-120b",
    }
    return Verdict.model_validate(fields | overrides)


def cite(passage_id: str, stance: str = "refutes") -> Citation:
    return Citation.model_validate({"passage_id": passage_id, "stance": stance})


def outputs(
    *,
    hits: list[ArchiveHit] | None = None,
    passages: list[Passage] | None = None,
    **overrides: Any,
) -> StageOutputs:
    """A complete, conflict-free case that routes to human review unless overridden."""
    fields: dict[str, Any] = {
        "claim": claim(),
        "media_match": MediaMatch(hits=hits if hits is not None else []),
        "evidence": Evidence(
            passages=passages if passages is not None else [passage("p1", "Kathmandu Post")]
        ),
        "verdict": verdict(confidence=0.5),
    }
    return StageOutputs(**(fields | overrides))
