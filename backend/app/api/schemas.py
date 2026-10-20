"""Request and response bodies. Public views never include model drafts."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, HttpUrl

from app.pipeline.contracts import ArchiveLabel, Route, VerdictLabel
from app.store.models import CaseStatus


class CaseCreated(BaseModel):
    id: str
    status: CaseStatus


class Source(BaseModel):
    name: str
    url: HttpUrl
    stance: str


class PublicClaim(BaseModel):
    claim: str
    claim_en: str
    places: list[str]
    claimed_date: date | None


class EarlierFootage(BaseModel):
    archive_label: ArchiveLabel
    original_context: str
    original_date: date | None
    source_url: HttpUrl


class PublishedVerdict(BaseModel):
    label: VerdictLabel
    rationale_en: str
    rationale_ne: str
    sources: list[Source]
    published_at: datetime
    # Shown only once a checker has published: unreviewed uploads and model readings stay
    # on the desk. Media are file names, served from /cases/{id}/media/{name}.
    claim: PublicClaim | None = None
    earlier_footage: list[EarlierFootage] = []
    media: list[str] = []


class PublicStep(BaseModel):
    """A status change without who made it or why: those stay on the desk."""

    at: datetime
    status: str


class PublicCase(BaseModel):
    id: str
    status: CaseStatus
    created_at: datetime
    text: str | None
    source_url: str | None
    media_count: int
    timeline: list[PublicStep]
    merged_into: str | None = None
    verdict: PublishedVerdict | None = None
    # The pasted link could not be opened, so the submitter is asked for the file.
    needs_media: bool = False


class DeskSummary(BaseModel):
    id: str
    created_at: datetime
    route: Route | None
    reasons: list[str]
    proposed_label: VerdictLabel | None
    claim_en: str | None
    text: str | None
    media_count: int


class DeskEvent(BaseModel):
    at: datetime
    actor: str
    from_status: str | None
    to_status: str
    note: str | None


class DeskCase(DeskSummary):
    status: CaseStatus
    source_url: str | None
    media: list[str]  # file names, served from /desk/cases/{id}/media/{name}
    outputs: dict[str, Any] | None
    decision: dict[str, Any] | None
    seconds: dict[str, Any] | None
    final_label: VerdictLabel | None
    events: list[DeskEvent]


class Action(StrEnum):
    PUBLISH = "publish"
    REJECT = "reject"
    REOPEN = "reopen"


class DecisionRequest(BaseModel):
    action: Action
    # Ignored when a checker signs in with their own code; the server knows their name.
    checker: str | None = None
    # For publish: omitted fields fall back to the model's draft.
    label: VerdictLabel | None = None
    rationale_en: str | None = None
    rationale_ne: str | None = None
    note: str | None = None
    # For publish: where the checker found the original footage; the archive keeps it.
    original_url: HttpUrl | None = None
