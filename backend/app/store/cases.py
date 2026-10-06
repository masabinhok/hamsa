"""Case store operations. Every status change writes a CaseEvent (architecture 4)."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, bindparam, create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.pipeline.contracts import (
    Claim,
    Duplicate,
    Evidence,
    MediaMatch,
    Route,
    RouteDecision,
    StageFailure,
    Verdict,
    VerdictLabel,
)
from app.router.route import StageOutputs
from app.store.models import (
    Base,
    Case,
    CaseEvent,
    CaseStatus,
    Channel,
    Job,
    JobState,
    Media,
    UTCDateTime,
    utcnow,
)

SYSTEM = "system"
LEASE = timedelta(minutes=10)  # a case takes ~20 s; a job running 10 min is presumed dead


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(url)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _sqlite_pragmas)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)


def _sqlite_pragmas(connection: Any, _record: Any) -> None:
    cursor = connection.cursor()
    # WAL lets the API read while the worker writes; they are separate processes.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


@dataclass(frozen=True)
class StoredMedia:
    filename: str
    sha256: str
    size_bytes: int


def save_media(media_root: Path, case_id: str, data: bytes, suffix: str) -> StoredMedia:
    digest = hashlib.sha256(data).hexdigest()
    filename = f"{digest[:16]}{suffix}"
    directory = media_root / case_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(data)
    return StoredMedia(filename=filename, sha256=digest, size_bytes=len(data))


def new_case_id() -> str:
    return secrets.token_hex(6)


def create_case(
    session: Session,
    case_id: str,
    channel: Channel,
    text_: str | None,
    source_url: str | None,
    media: list[StoredMedia],
) -> Case:
    case = Case(id=case_id, channel=channel, text=text_, source_url=source_url)
    case.media = [
        Media(filename=m.filename, sha256=m.sha256, size_bytes=m.size_bytes) for m in media
    ]
    session.add_all([case, Job(case_id=case_id)])
    _event(session, case, SYSTEM, None, CaseStatus.RECEIVED, f"submitted via {channel}")
    return case


def claim_job(session: Session, now: datetime | None = None) -> tuple[int, str] | None:
    """Atomically take the oldest due job, or one whose lease expired (a dead worker's)."""
    now = now or utcnow()
    row = session.execute(
        text(
            """
            UPDATE jobs SET state = :running, lease_until = :lease, attempts = attempts + 1
            WHERE id = (
                SELECT id FROM jobs
                WHERE (state = :queued AND not_before <= :now)
                   OR (state = :running AND lease_until < :now)
                ORDER BY not_before, id LIMIT 1
            )
            RETURNING id, case_id
            """
        ).bindparams(
            # Typed so the raw SQL compares in the same format the ORM stores.
            bindparam("now", type_=UTCDateTime()),
            bindparam("lease", type_=UTCDateTime()),
        ),
        {
            "running": JobState.RUNNING.value,
            "queued": JobState.QUEUED.value,
            "now": now,
            "lease": now + LEASE,
        },
    ).one_or_none()
    if row is None:
        return None
    case = session.get_one(Case, row.case_id)
    if case.status is CaseStatus.RECEIVED:
        _event(session, case, SYSTEM, case.status, CaseStatus.PROCESSING, None)
    return row.id, row.case_id


def complete_job(
    session: Session,
    job_id: int,
    case: Case,
    outputs: StageOutputs,
    decision: RouteDecision,
    seconds: dict[str, float],
) -> None:
    job = session.get_one(Job, job_id)
    job.state, job.lease_until = JobState.DONE, None
    case.outputs = outputs_to_json(outputs)
    case.decision = decision.model_dump(mode="json")
    case.seconds = seconds
    case.route = decision.route.value
    status = CaseStatus.ROUTED
    if decision.route is Route.MERGE:
        case.merged_into, status = decision.merge_into, CaseStatus.MERGED
    _event(
        session,
        case,
        SYSTEM,
        case.status,
        status,
        f"{decision.route}: {'; '.join(decision.reasons)}",
    )


def requeue_job(session: Session, job_id: int, error: str, delay: timedelta) -> None:
    job = session.get_one(Job, job_id)
    job.state, job.lease_until = JobState.QUEUED, None
    job.not_before = utcnow() + delay
    job.last_error = error


class DecisionError(Exception):
    pass


def publish(
    session: Session,
    case: Case,
    checker: str,
    label: VerdictLabel,
    rationale_en: str,
    rationale_ne: str,
    note: str | None,
) -> None:
    if case.status is not CaseStatus.ROUTED:
        raise DecisionError(f"case is {case.status}, only routed cases can be published")
    case.final_label = label.value
    case.final_rationale_en, case.final_rationale_ne = rationale_en, rationale_ne
    _event(session, case, checker, case.status, CaseStatus.PUBLISHED, note)


def reject(session: Session, case: Case, checker: str, note: str) -> None:
    if case.status is not CaseStatus.ROUTED:
        raise DecisionError(f"case is {case.status}, only routed cases can be rejected")
    _event(session, case, checker, case.status, CaseStatus.REJECTED, note)


def reopen(session: Session, case: Case, checker: str, note: str) -> None:
    """Back to the desk, e.g. when new evidence contradicts a published verdict."""
    if case.status not in (CaseStatus.PUBLISHED, CaseStatus.REJECTED):
        raise DecisionError(f"case is {case.status}, only closed cases can be reopened")
    case.final_label = case.final_rationale_en = case.final_rationale_ne = None
    _event(session, case, checker, case.status, CaseStatus.ROUTED, note)


def desk_queue(session: Session, route: Route | None = None) -> list[Case]:
    """Routed cases, fast-track first (one-click approvals), oldest first within a route."""
    query = select(Case).where(Case.status == CaseStatus.ROUTED)
    if route is not None:
        query = query.where(Case.route == route.value)
    cases = list(session.scalars(query.order_by(Case.created_at)))
    order = [Route.FAST_TRACK, Route.HUMAN_REVIEW, Route.INVESTIGATE, Route.DISMISS]
    return sorted(cases, key=lambda c: order.index(Route(c.route)) if c.route else len(order))


def published(session: Session, limit: int = 50) -> list[Case]:
    query = (
        select(Case)
        .where(Case.status == CaseStatus.PUBLISHED)
        .order_by(Case.updated_at.desc())
        .limit(limit)
    )
    return list(session.scalars(query))


def outputs_to_json(outputs: StageOutputs) -> dict[str, Any]:
    def dump(model: Any) -> Any:
        return None if model is None else model.model_dump(mode="json")

    return {
        "failures": [f.model_dump(mode="json") for f in outputs.failures],
        "duplicate": dump(outputs.duplicate),
        "claim": dump(outputs.claim),
        "media_match": dump(outputs.media_match),
        "evidence": dump(outputs.evidence),
        "verdict": dump(outputs.verdict),
    }


def outputs_from_json(data: dict[str, Any]) -> StageOutputs:
    def load[T: BaseModel](model: type[T], value: Any) -> T | None:
        return None if value is None else model.model_validate(value)

    return StageOutputs(
        failures=tuple(StageFailure.model_validate(f) for f in data["failures"]),
        duplicate=load(Duplicate, data["duplicate"]),
        claim=load(Claim, data["claim"]),
        media_match=load(MediaMatch, data["media_match"]),
        evidence=load(Evidence, data["evidence"]),
        verdict=load(Verdict, data["verdict"]),
    )


def _event(
    session: Session,
    case: Case,
    actor: str,
    before: CaseStatus | None,
    after: CaseStatus,
    note: str | None,
) -> None:
    case.status = after
    session.add(
        CaseEvent(
            case_id=case.id,
            actor=actor,
            from_status=before.value if before else None,
            to_status=after.value,
            note=note,
        )
    )
