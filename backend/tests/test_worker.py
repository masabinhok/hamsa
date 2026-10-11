from collections.abc import Sequence
from pathlib import Path

import pytest

from app.pipeline.contracts import Route, Stage, StageFailure
from app.pipeline.run import Result
from app.router.route import StageOutputs
from app.store.cases import Database
from app.store.models import Case, CaseStatus, Job, JobState
from app.worker import MAX_ATTEMPTS, process_next
from tests.stored import add_case, database, routed_result


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return database(tmp_path)


def transient_failure(text: str | None, media: Sequence[Path]) -> Result:
    failure = StageFailure(stage=Stage.EXTRACT, error="ConnectError: ollama down", transient=True)
    return routed_result(StageOutputs(failures=(failure,)))


def force_due(db: Database) -> None:
    with db.session.begin() as session:
        job = session.get_one(Job, 1)
        job.not_before = job.not_before.replace(year=2000)


def test_nothing_to_do(db: Database, tmp_path: Path) -> None:
    assert process_next(db, lambda t, m: routed_result(), tmp_path) is None


def test_runs_the_pipeline_with_the_case_text_and_media_paths(db: Database, tmp_path: Path) -> None:
    add_case(db, "c1", text="बाढी आयो")
    seen: list[tuple[str | None, list[Path]]] = []

    def runner(text: str | None, media: Sequence[Path]) -> Result:
        seen.append((text, list(media)))
        return routed_result()

    assert process_next(db, runner, tmp_path) == "c1"
    assert seen == [("बाढी आयो", [])]
    with db.session() as session:
        assert session.get_one(Case, "c1").status is CaseStatus.ROUTED


def test_transient_failure_is_retried_then_sent_to_a_human(db: Database, tmp_path: Path) -> None:
    add_case(db, "c1")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        force_due(db)
        process_next(db, transient_failure, tmp_path)
        with db.session() as session:
            job = session.get_one(Job, 1)
            case = session.get_one(Case, "c1")
            if attempt < MAX_ATTEMPTS:
                assert job.state is JobState.QUEUED
                assert job.last_error == "ConnectError: ollama down"
            else:
                assert job.state is JobState.DONE
                assert case.route == Route.HUMAN_REVIEW.value


def test_pipeline_bug_routes_to_a_human_instead_of_looping(db: Database, tmp_path: Path) -> None:
    add_case(db, "c1")

    def broken(text: str | None, media: Sequence[Path]) -> Result:
        raise ValueError("router bug")

    process_next(db, broken, tmp_path)
    with db.session() as session:
        case = session.get_one(Case, "c1")
        assert case.route == Route.HUMAN_REVIEW.value
        assert case.decision is not None
        assert case.decision["reasons"] == ["pipeline error: ValueError"]
