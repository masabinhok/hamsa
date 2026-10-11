"""Run one post through every stage and route it (architecture section 3).

Any stage error is recorded as a StageFailure, which the router sends to a human:
a failure never produces a verdict on its own.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
from qdrant_client.http.exceptions import ResponseHandlingException

from app.ingest.frames import Frame, frames_of
from app.pipeline.contracts import (
    Claim,
    Evidence,
    MediaMatch,
    RouteDecision,
    Stage,
    StageFailure,
    Verdict,
)
from app.pipeline.media_match import ArchiveIndex, Embed, match_media
from app.pipeline.retrieve import EmbedText, EvidenceStore, retrieve
from app.pipeline.verdict import Reasoner, judge
from app.router.route import StageOutputs, route

Extract = Callable[[str | None, Sequence[Frame]], Claim]


@dataclass(frozen=True)
class Pipeline:
    extract: Extract
    archive: ArchiveIndex
    embed_image: Embed
    evidence: EvidenceStore
    embed_text: EmbedText
    reasoners: Sequence[tuple[Reasoner, str]]
    incident_start: date


@dataclass
class Result:
    outputs: StageOutputs
    decision: RouteDecision
    seconds: dict[str, float] = field(default_factory=dict[str, float])


def is_transient(error: Exception) -> bool:
    """A local service was unreachable or overloaded, so retrying later may succeed."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, httpx.TransportError | ResponseHandlingException | ConnectionError)


def run(
    pipeline: Pipeline, text: str | None, media: Sequence[Path], seen_on: date | None = None
) -> Result:
    """`seen_on` is the post's date when known (eval items); otherwise today, the submission."""
    seconds: dict[str, float] = {}
    failures: list[StageFailure] = []

    def stage[T](name: Stage, work: Callable[[], T]) -> T | None:
        started = time.monotonic()
        try:
            return work()
        except Exception as error:  # every stage error becomes a recorded failure
            failures.append(
                StageFailure(
                    stage=name,
                    error=f"{type(error).__name__}: {error}",
                    transient=is_transient(error),
                )
            )
            return None
        finally:
            seconds[name.value] = round(time.monotonic() - started, 2)

    def finish(
        claim: Claim | None = None,
        media_match: MediaMatch | None = None,
        evidence: Evidence | None = None,
        verdict: Verdict | None = None,
    ) -> Result:
        outputs = StageOutputs(
            failures=tuple(failures),
            claim=claim,
            media_match=media_match,
            evidence=evidence,
            verdict=verdict,
            seen_on=seen_on or date.today(),
        )
        return Result(outputs=outputs, decision=route(outputs), seconds=seconds)

    frames = stage(Stage.INGEST, lambda: [f for path in media for f in frames_of(path)])
    if frames is None:
        return finish()

    claim = stage(Stage.EXTRACT, lambda: pipeline.extract(text, frames))
    if claim is None or not claim.checkable:
        return finish(claim=claim)

    matched: MediaMatch | None = stage(
        Stage.MEDIA_MATCH, lambda: match_media(frames, pipeline.archive, pipeline.embed_image)
    )
    evidence: Evidence | None = stage(
        Stage.RETRIEVE,
        lambda: retrieve(claim, pipeline.evidence, pipeline.embed_text, pipeline.incident_start),
    )
    if matched is None or evidence is None:
        return finish(claim=claim, media_match=matched, evidence=evidence)

    verdict: Verdict | None = stage(
        Stage.VERDICT,
        lambda: judge(claim, matched, evidence, pipeline.reasoners, has_media=bool(frames)),
    )
    return finish(claim=claim, media_match=matched, evidence=evidence, verdict=verdict)
