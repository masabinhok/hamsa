"""Case store operations. Every status change writes a CaseEvent (architecture 4)."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel
from sqlalchemy import Engine, bindparam, create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.pipeline.contracts import (
    Claim,
    Duplicate,
    DuplicateBasis,
    Evidence,
    MediaMatch,
    Route,
    RouteDecision,
    StageFailure,
    Verdict,
    VerdictLabel,
)
from app.pipeline.duplicate import OpenClaim
from app.router.route import StageOutputs
from app.store.models import (
    Base,
    Case,
    CaseEvent,
    CaseStatus,
    Channel,
    Job,
    JobState,
    Lesson,
    Media,
    PostId,
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


def add_sent_media(session: Session, case: Case, media: list[StoredMedia]) -> None:
    """The submitter sent the file behind a link the worker could not open: check it again,
    on the same case, so the desk is not left with an empty one beside a new one."""
    case.media += [
        Media(filename=m.filename, sha256=m.sha256, size_bytes=m.size_bytes) for m in media
    ]
    job = session.scalars(select(Job).where(Job.case_id == case.id)).one()
    job.state, job.attempts, job.not_before = JobState.QUEUED, 0, utcnow()
    job.lease_until = job.last_error = None
    _event(session, case, SYSTEM, case.status, CaseStatus.RECEIVED, "the sender added the media")


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
    original_url: str | None = None,
) -> None:
    if case.status is not CaseStatus.ROUTED:
        raise DecisionError(f"case is {case.status}, only routed cases can be published")
    case.final_label = label.value
    case.final_rationale_en, case.final_rationale_ne = rationale_en, rationale_ne
    _event(session, case, checker, case.status, CaseStatus.PUBLISHED, note)
    # Every verdict teaches the archive, so the next repost is matched without a checker.
    session.add(Lesson(case_id=case.id, original_url=original_url))


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


OPEN = (CaseStatus.RECEIVED, CaseStatus.PROCESSING, CaseStatus.ROUTED)


DECIDED = (CaseStatus.PUBLISHED, CaseStatus.REJECTED)
# Query parameters that say who shared a post or how, never which post it is.
TRACKING = frozenset(
    {"fbclid", "mibextid", "rdid", "ref", "si", "feature", "t", "s", "igsh", "igshid"}
    | {"is_from_webapp", "sender_device", "_r", "_t", "share_url", "img_index"}
)


def normalize_url(url: str) -> str:
    """One spelling per post link: the same post forwarded from the app, the mobile site or
    a share sheet differs only in host prefix and tracking parameters."""
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    host = re.sub(r"^(m|mobile|web|vm)\.", "www.", host)
    host = {"twitter.com": "x.com", "www.twitter.com": "x.com", "www.x.com": "x.com"}.get(
        host, host
    )
    path = parts.path.rstrip("/")
    if host == "youtu.be":
        host, path, query = "www.youtube.com", "/watch", [("v", path.lstrip("/"))]
    else:
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query)
            if key.lower() not in TRACKING and not key.lower().startswith(("utm_", "__"))
        ]
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def same_post(session: Session, case: Case) -> Duplicate | None:
    """The earliest earlier report of this post, open or decided, for the case to merge into.

    The same link or platform post id is the same post. The same file is too while that
    report is open; once it is decided, only with the same words or none: a new caption can
    make genuine footage a false claim, so that copy is checked afresh (the archive knows the
    footage). Only earlier cases: otherwise a report would merge into its own later copy.
    """
    earlier = select(Case).where(Case.created_at < case.created_at).order_by(Case.created_at)
    found: list[tuple[Case, DuplicateBasis]] = []
    if case.source_url:
        link = normalize_url(case.source_url)
        # shortcut: normalises every earlier link per case; store it once there are thousands.
        linked = session.scalars(earlier.where(Case.source_url.is_not(None)))
        found += [
            (c, DuplicateBasis.LINK) for c in linked if normalize_url(c.source_url or "") == link
        ]
    if post_id := session.scalar(select(PostId.post_id).where(PostId.case_id == case.id)):
        same_id = session.scalars(earlier.join(PostId).where(PostId.post_id == post_id))
        found += [(c, DuplicateBasis.LINK) for c in same_id]
    if digests := [m.sha256 for m in case.media]:
        same_file = session.scalars(earlier.join(Media).where(Media.sha256.in_(digests)))
        found += [(c, DuplicateBasis.MEDIA) for c in same_file]

    for earliest, basis in sorted(found, key=lambda pair: pair[0].created_at):
        target = answered_by(session, earliest)
        if target.status in OPEN or (
            target.status in DECIDED
            and (basis is DuplicateBasis.LINK or _same_words(case.text, target.text))
        ):
            return Duplicate(case_id=target.id, basis=basis)
    return None


def answered_by(session: Session, case: Case) -> Case:
    """The case whose verdict answers this one: itself, or the report it was merged into."""
    for _ in range(5):  # merges point at earlier cases, so this is a short chain
        if case.merged_into is None:
            break
        case = session.get_one(Case, case.merged_into)
    return case


def _same_words(new: str | None, old: str | None) -> bool:
    return not (new and new.strip()) or " ".join(new.split()) == " ".join((old or "").split())


def open_claims(session: Session) -> list[OpenClaim]:
    """Claims of the cases waiting on the desk, for the pipeline's duplicate check."""
    claims: list[OpenClaim] = []
    for case in session.scalars(select(Case).where(Case.status == CaseStatus.ROUTED)):
        claim = outputs_from_json(case.outputs).claim if case.outputs else None
        if claim and claim.checkable:
            claims.append(OpenClaim(case.id, claim.claim_en, tuple(claim.places)))
    return claims


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
        "seen_on": outputs.seen_on.isoformat() if outputs.seen_on else None,
        "posted_on": outputs.posted_on.isoformat() if outputs.posted_on else None,
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
        # Absent from cases stored before the post's date was kept.
        seen_on=_day(data.get("seen_on")),
        posted_on=_day(data.get("posted_on")),
    )


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


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
