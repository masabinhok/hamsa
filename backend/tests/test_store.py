from datetime import date, timedelta
from pathlib import Path

import pytest

from app.pipeline.contracts import Route, VerdictLabel
from app.store.cases import (
    LEASE,
    Database,
    DecisionError,
    claim_job,
    desk_queue,
    outputs_from_json,
    outputs_to_json,
    publish,
    reject,
    reopen,
    requeue_job,
    save_media,
)
from app.store.models import Case, CaseStatus, Job, JobState, utcnow
from tests.factories import cite, hit, outputs, passage, verdict
from tests.stored import add_case, add_routed_case, database, routed_result


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return database(tmp_path)


def statuses(db: Database, case_id: str) -> list[str]:
    with db.session() as session:
        return [e.to_status for e in session.get_one(Case, case_id).events]


def test_new_case_is_received_with_a_queued_job(db: Database) -> None:
    add_case(db, "c1")
    with db.session() as session:
        case = session.get_one(Case, "c1")
        assert case.status is CaseStatus.RECEIVED
        assert session.get_one(Job, 1).state is JobState.QUEUED
    assert statuses(db, "c1") == ["received"]


def test_claim_takes_oldest_job_once(db: Database) -> None:
    add_case(db, "c1")
    add_case(db, "c2")
    with db.session.begin() as session:
        assert claim_job(session) == (1, "c1")
    with db.session.begin() as session:
        assert claim_job(session) == (2, "c2")
    with db.session.begin() as session:
        assert claim_job(session) is None
    assert statuses(db, "c1") == ["received", "processing"]


def test_expired_lease_is_reclaimed_from_a_dead_worker(db: Database) -> None:
    add_case(db, "c1")
    with db.session.begin() as session:
        claim_job(session)
    with db.session.begin() as session:
        assert claim_job(session) is None
        assert claim_job(session, now=utcnow() + LEASE + timedelta(seconds=1)) == (1, "c1")
        assert session.get_one(Job, 1).attempts == 2


def test_requeued_job_waits_for_its_backoff(db: Database) -> None:
    add_case(db, "c1")
    with db.session.begin() as session:
        claim_job(session)
        requeue_job(session, 1, "ConnectError: ollama down", timedelta(seconds=30))
    with db.session.begin() as session:
        assert claim_job(session) is None
        assert claim_job(session, now=utcnow() + timedelta(seconds=31)) == (1, "c1")
        assert session.get_one(Job, 1).last_error == "ConnectError: ollama down"


def test_completed_job_stores_outputs_decision_and_audit_note(db: Database) -> None:
    decision = add_routed_case(db, "c1")
    with db.session() as session:
        case = session.get_one(Case, "c1")
        assert case.status is CaseStatus.ROUTED
        assert case.route == decision.route.value
        assert case.seconds == {"extract": 1.0}
        assert session.get_one(Job, 1).state is JobState.DONE
        assert case.events[-1].note == f"{decision.route}: {decision.reasons[0]}"


def test_outputs_round_trip_through_json() -> None:
    original = outputs(
        hits=[hit()],
        passages=[passage("p1", "Nepal Factcheck")],
        verdict=verdict("false", 0.9, citations=[cite("p1")]),
        seen_on=date(2026, 8, 27),
        posted_on=date(2026, 8, 27),  # the router needs it to judge figures
    )
    assert outputs_from_json(outputs_to_json(original)) == original


def test_publish_reject_and_reopen_follow_the_lifecycle(db: Database) -> None:
    add_routed_case(db, "c1")
    with db.session.begin() as session:
        case = session.get_one(Case, "c1")
        publish(session, case, "sita", VerdictLabel.FALSE, "Old video.", "पुरानो भिडियो।", None)
        with pytest.raises(DecisionError, match="only routed"):
            reject(session, case, "sita", "changed my mind")
        reopen(session, case, "sita", "new evidence")
        assert case.final_label is None
        reject(session, case, "ram", "not a real claim")
    assert statuses(db, "c1")[-3:] == ["published", "routed", "rejected"]


def test_unrouted_case_cannot_be_published(db: Database) -> None:
    add_case(db, "c1")
    with db.session.begin() as session, pytest.raises(DecisionError, match="received"):
        publish(session, session.get_one(Case, "c1"), "sita", VerdictLabel.TRUE, "a", "b", None)


def test_desk_queue_puts_fast_track_first(db: Database) -> None:
    add_routed_case(db, "review")  # default outputs route to human review
    fast = outputs(hits=[hit()], verdict=verdict("false", 0.5))
    add_routed_case(db, "fast", routed_result(fast))
    with db.session() as session:
        assert [c.id for c in desk_queue(session)] == ["fast", "review"]
        assert [c.id for c in desk_queue(session, Route.HUMAN_REVIEW)] == ["review"]


def test_media_is_stored_by_content_hash(tmp_path: Path) -> None:
    stored = save_media(tmp_path, "c1", b"jpeg bytes", ".jpg")
    assert stored.filename.endswith(".jpg")
    assert (tmp_path / "c1" / stored.filename).read_bytes() == b"jpeg bytes"
    assert stored.size_bytes == 10


def test_datetimes_load_as_aware_utc(db: Database) -> None:
    add_case(db, "c1")
    with db.session() as session:
        created = session.get_one(Case, "c1").created_at
    assert created.utcoffset() == timedelta(0)
