"""Request and response bodies. Public views never include model drafts."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, HttpUrl

from app.pipeline.contracts import Route, VerdictLabel
from app.store.models import CaseStatus


class CaseCreated(BaseModel):
    id: str
    status: CaseStatus


class Source(BaseModel):
    name: str
    url: HttpUrl
    stance: str


class PublishedVerdict(BaseModel):
    label: VerdictLabel
    rationale_en: str
    rationale_ne: str
    sources: list[Source]
    published_at: datetime


class PublicCase(BaseModel):
    id: str
    status: CaseStatus
    verdict: PublishedVerdict | None = None


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
    checker: str
    # For publish: omitted fields fall back to the model's draft.
    label: VerdictLabel | None = None
    rationale_en: str | None = None
    rationale_ne: str | None = None
    note: str | None = None
