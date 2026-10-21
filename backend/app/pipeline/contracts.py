"""Typed outputs of each pipeline stage. See docs/architecture.md section 3.

Every model response is parsed into one of these; a response that does not
validate is a stage failure, never a silent default.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, model_validator

RATIONALE_MAX_WORDS = 120


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


NonEmptyStr = Annotated[str, Field(min_length=1)]


# 3.2 claim extraction


class ClaimedNumber(Contract):
    value: float
    unit: str | None = None
    refers_to: NonEmptyStr


class Claim(Contract):
    claim: NonEmptyStr
    claim_en: NonEmptyStr
    places: list[NonEmptyStr] = []
    claimed_date: date | None = None
    # As written: Gregorian (2015) or Bikram Sambat (2072); the router tells them apart.
    claimed_year: int | None = None
    numbers: list[ClaimedNumber] = []
    visible_text: list[NonEmptyStr] = []
    watermarks: list[NonEmptyStr] = []
    handles: list[NonEmptyStr] = []
    checkable: bool


# 3.3 media match


class ArchiveLabel(StrEnum):
    PRIOR = "prior"  # before the incident, or from elsewhere
    VERIFIED_GENUINE = "verified_genuine"  # confirmed footage of this incident


class ArchiveHit(Contract):
    archive_id: NonEmptyStr
    frame_index: Annotated[int, Field(ge=0)]
    phash_distance: Annotated[int | None, Field(ge=0, le=64)] = None
    cosine: Annotated[float | None, Field(ge=-1.0, le=1.0)] = None
    # ORB keypoint matches that agree on one geometric transform between the frames.
    inliers: Annotated[int | None, Field(ge=0)] = None
    # Where each side of the best frame pair sits, so the desk can show them together.
    post_seconds: Annotated[float | None, Field(ge=0)] = None
    archive_seconds: Annotated[float | None, Field(ge=0)] = None
    archive_media: str | None = None  # path under data/, served to checkers only
    archive_label: ArchiveLabel
    original_context: NonEmptyStr
    original_date: date | None = None
    source_url: HttpUrl

    @model_validator(mode="after")
    def _has_a_score(self) -> Self:
        if self.phash_distance is None and self.cosine is None:
            raise ValueError("a hit needs a phash_distance, a cosine, or both")
        return self


class MediaMatch(Contract):
    hits: list[ArchiveHit] = []


# 3.4 duplicate check


class DuplicateBasis(StrEnum):
    MEDIA = "media"
    CLAIM = "claim"


class Duplicate(Contract):
    case_id: NonEmptyStr
    basis: DuplicateBasis


# 3.5 evidence retrieval


class SourceKind(StrEnum):
    NEWS = "news"
    OFFICIAL = "official"
    FACT_CHECK = "fact_check"
    # Found by open web search: shown as evidence, never counted as an independent source.
    WEB = "web"


class Passage(Contract):
    passage_id: NonEmptyStr
    source: NonEmptyStr  # outlet or body, e.g. "Kathmandu Post"; independence is per source
    source_kind: SourceKind
    url: HttpUrl
    # Shown with the passage: a fact-check's headline usually states its verdict.
    title: str | None = None
    published_at: datetime | None = None
    text: NonEmptyStr
    score: float


class Evidence(Contract):
    passages: Annotated[list[Passage], Field(max_length=8)] = []

    @model_validator(mode="after")
    def _ids_are_unique(self) -> Self:
        ids = [p.passage_id for p in self.passages]
        if len(ids) != len(set(ids)):
            raise ValueError("passage ids must be unique")
        return self

    def by_id(self, passage_id: str) -> Passage | None:
        return next((p for p in self.passages if p.passage_id == passage_id), None)


# 3.6 verdict


class VerdictLabel(StrEnum):
    FALSE = "false"
    MISLEADING = "misleading"
    TRUE = "true"
    UNVERIFIABLE = "unverifiable"


class Stance(StrEnum):
    """What a cited passage says about the claim."""

    SUPPORTS = "supports"
    REFUTES = "refutes"


class MediaFinding(StrEnum):
    """What the evidence shows about the post's photo or video."""

    SHOWS_CLAIM = "shows_claim"  # a frame match or fact-check places it in this event
    ELSEWHERE = "elsewhere"  # another place, year, or event
    AI_GENERATED = "ai_generated"
    NOT_ESTABLISHED = "not_established"
    NO_MEDIA = "no_media"


class EventFinding(StrEnum):
    """Whether the event the post describes happened, as described."""

    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    NOT_FOUND = "not_found"


class NumberFinding(StrEnum):
    """Figures change as counts are updated, so they are judged as of the post's date."""

    CONSISTENT = "consistent"
    CONTRADICTED = "contradicted"
    NOT_ESTABLISHED = "not_established"
    NONE_CLAIMED = "none_claimed"


class Citation(Contract):
    passage_id: NonEmptyStr
    stance: Stance


def _within_word_limit(text: str) -> str:
    if len(text.split()) > RATIONALE_MAX_WORDS:
        raise ValueError(f"rationale is limited to {RATIONALE_MAX_WORDS} words")
    return text


class Verdict(Contract):
    label: VerdictLabel
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    rationale_en: Annotated[NonEmptyStr, AfterValidator(_within_word_limit)]
    rationale_ne: Annotated[NonEmptyStr, AfterValidator(_within_word_limit)]
    citations: list[Citation] = []
    # None on verdicts drafted before findings were asked for.
    media_finding: MediaFinding | None = None
    event_finding: EventFinding | None = None
    number_finding: NumberFinding | None = None
    model: NonEmptyStr
    # True when the hosted model was unavailable and the local model judged instead.
    # Measured weaker (it read "no evidence" as "false"), so the router never fast-tracks
    # on its judgement alone.
    fallback: bool = False
    # Set when the Nepali rationale may not say what the English says (or could not be
    # checked); the Nepali is published to the public, so a checker must read it first.
    nepali_issue: str | None = None

    def unknown_citations(self, evidence: Evidence) -> list[str]:
        """Cited ids absent from the evidence the model was given: hallucinations."""
        return [c.passage_id for c in self.citations if evidence.by_id(c.passage_id) is None]


# failures and routing


class Stage(StrEnum):
    INGEST = "ingest"
    EXTRACT = "extract"
    MEDIA_MATCH = "media_match"
    DEDUP = "dedup"
    RETRIEVE = "retrieve"
    VERDICT = "verdict"


class StageFailure(Contract):
    stage: Stage
    error: NonEmptyStr
    # A service was unreachable (Ollama, Qdrant): the worker retries the job instead of
    # routing it. Permanent failures (an undecodable video) go straight to a human.
    transient: bool = False


class Route(StrEnum):
    MERGE = "merge"
    DISMISS = "dismiss"
    FAST_TRACK = "fast_track"
    HUMAN_REVIEW = "human_review"
    INVESTIGATE = "investigate"


class RouteDecision(Contract):
    route: Route
    reasons: Annotated[list[NonEmptyStr], Field(min_length=1)]
    merge_into: str | None = None
    proposed_label: VerdictLabel | None = None

    @model_validator(mode="after")
    def _merge_has_target(self) -> Self:
        if (self.route is Route.MERGE) != (self.merge_into is not None):
            raise ValueError("merge_into is required for merge and only for merge")
        return self
